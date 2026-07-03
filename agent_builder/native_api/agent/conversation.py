# omnis_hermes/agent/conversation.py
import json

import frappe
from frappe.utils import now_datetime
from frappe.realtime import get_user_room

SESSION_DOCTYPE = "Agent session"


def _gen_id() -> str:
    return frappe.generate_hash(length=16)


class Conversation:
    def __init__(self, session_id=None, user=None):
        self.user = user or frappe.session.user or "Guest"
        self.room = get_user_room(self.user)

        if session_id and frappe.db.exists(SESSION_DOCTYPE, session_id):
            self.doc = frappe.get_doc(SESSION_DOCTYPE, session_id)
        else:
            self.doc = frappe.new_doc(SESSION_DOCTYPE)
            self.doc.user = self.user
            if session_id:
                self.doc.name = session_id
            self.doc.insert(ignore_permissions=True)

        self.session_id = self.doc.name
        self.system_prompt = None
        self._reasoning_buffer = ""
        self._last_message_id = None

    # ── History reconstruction ───────────────────────────

    def get_messages(self):
        """Rebuild the OpenAI-style message list from the two normalized tables."""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Index tool calls by their parent message_id, preserving insertion order.
        tool_calls_by_parent: dict[str, list] = {}
        for tc in self.doc.tool_calls:
            tool_calls_by_parent.setdefault(tc.parent_message, []).append(tc)

        # Buffer to accumulate reasoning so we can attach it to the next assistant turn
        pending_reasoning = []

        for row in self.doc.messages:
            if row.role == "reasoning":
                if row.content:
                    pending_reasoning.append(row.content.strip())
                continue

            if row.role == "assistant":
                content = row.content or ""
                tc_rows = tool_calls_by_parent.get(row.message_id, [])

                # Re-attach preceding reasoning into the assistant's content block.
                # Wrapping it in <think> tags is the industry standard for OpenRouter 
                # and open-weight reasoning models (like DeepSeek-R1).
                if pending_reasoning:
                    reasoning_text = "\n\n".join(pending_reasoning)
                    if content:
                        content = f"<think>\n{reasoning_text}\n</think>\n\n{content}"
                    else:
                        # Even if content is empty (e.g. only tool calls), pass the reasoning
                        content = f"<think>\n{reasoning_text}\n</think>"
                    pending_reasoning = []

                msg = {"role": "assistant", "content": content}

                if tc_rows:
                    msg["tool_calls"] = [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {
                                "name": tc.tool_name,
                                "arguments": tc.arguments or "{}",
                            },
                        }
                        for tc in tc_rows
                    ]
                messages.append(msg)

                # Synthesize one tool-role message per *completed* tool call,
                # immediately after the assistant turn that requested it.
                for tc in tc_rows:
                    if tc.status not in ("success", "error"):
                        continue
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "name": tc.tool_name,
                        "content": (tc.error if tc.status == "error"
                                    else tc.result) or "",
                    })
            else:
                # For User or System messages, clear reasoning buffer if out of order
                pending_reasoning = [] 
                messages.append({"role": row.role, "content": row.content or ""})

        return messages

    # ── Mutators ─────────────────────────────────────────

    def set_system(self, text):
        self.system_prompt = text

    def add_user_message(self, text):
        if not self.doc.title:
            self.doc.title = (text or "")[:72]
        msg_id = _gen_id()
        self.doc.append("messages", {
            "message_id": msg_id,
            "role": "user",
            "content": text,
            "timestamp": now_datetime(),
        })
        self._last_message_id = msg_id
        self._emit("user", text)

    def add_assistant_message(self, message_obj, streamed=False):
        self._flush_reasoning()

        content = message_obj.get("content") or ""
        tool_calls = message_obj.get("tool_calls") or []

        msg_id = _gen_id()
        self.doc.append("messages", {
            "message_id": msg_id,
            "role": "assistant",
            "content": content,
            "is_error": bool(message_obj.get("is_error")),
            "timestamp": now_datetime(),
        })
        self._last_message_id = msg_id

        for tc in tool_calls:
            fn = tc.get("function", {})
            self.doc.append("tool_calls", {
                "call_id": tc.get("id") or _gen_id(),
                "parent_message": msg_id,
                "tool_name": fn.get("name", ""),
                "arguments": fn.get("arguments") or "{}",
                "status": "pending",
                "started_at": now_datetime(),
            })

        if content and not streamed:
            self._emit("assistant", content)

    # ── Streaming hooks ──────────────────────────────────

    def emit_token(self, delta):
        if not delta:
            return
        frappe.publish_realtime(
            event="agent_token",
            message={"session_id": self.session_id, "delta": delta},
            room=self.room,
        )

    def emit_reasoning(self, delta):
        if not delta:
            return
        self._reasoning_buffer += delta
        frappe.publish_realtime(
            event="agent_reasoning",
            message={"session_id": self.session_id, "delta": delta},
            room=self.room,
        )

    # ── Tool lifecycle ───────────────────────────────────

    def emit_tool_start(self, tool_call_id, tool_name, args):
        self._flush_reasoning()

        # Persist the transition pending → running.
        for tc in self.doc.tool_calls:
            if tc.call_id == tool_call_id and tc.status == "pending":
                tc.status = "running"
                tc.started_at = now_datetime()
                break

        self._publish_event({
            "type": "tool_start",
            "tool": tool_name,
            "args": json.dumps(args) if isinstance(args, dict) else str(args),
            "call_id": tool_call_id,
        })

    def add_tool_result(self, tool_call_id, name, content, elapsed_ms=None):
        is_error = isinstance(content, str) and content.startswith("Error:")
        now = now_datetime()

        for tc in self.doc.tool_calls:
            if tc.call_id != tool_call_id:
                continue

            tc.status = "error" if is_error else "success"
            tc.completed_at = now

            if is_error:
                tc.error = content
            else:
                tc.result = content

            if elapsed_ms is None and tc.started_at:
                elapsed_ms = int((now - tc.started_at).total_seconds() * 1000)
            tc.elapsed_ms = elapsed_ms
            break

        payload = {
            "type": "tool_done",
            "tool": name,
            "call_id": tool_call_id,
            "elapsed_ms": elapsed_ms,
        }
        payload["error" if is_error else "result"] = (
            content[:500] if is_error else str(content)[:500]
        )
        self._publish_event(payload)

    # ── Terminal events ──────────────────────────────────

    def emit_done(self, response):
        frappe.publish_realtime(
            event="agent_done",
            message={"session_id": self.session_id, "response": response},
            room=self.room,
        )

    def emit_error(self, error_text):
        frappe.publish_realtime(
            event="agent_error",
            message={"session_id": self.session_id, "response": error_text},
            room=self.room,
        )

    # ── Persistence ──────────────────────────────────────

    def save(self):
        self._flush_reasoning()
        self.doc.last_active = now_datetime()
        self.doc.message_count = len(self.doc.messages)
        self.doc.tool_call_count = len(self.doc.tool_calls)
        self.doc.save(ignore_permissions=True)
        frappe.db.commit()

    # ── Private ──────────────────────────────────────────

    def _flush_reasoning(self):
        if not self._reasoning_buffer:
            return
        self.doc.append("messages", {
            "message_id": _gen_id(),
            "role": "reasoning",
            "content": self._reasoning_buffer,
            "timestamp": now_datetime(),
        })
        self._reasoning_buffer = ""

    def _emit(self, role, content, **kwargs):
        if not content:
            return
        frappe.publish_realtime(
            event="agent_message",
            message={"session_id": self.session_id, "role": role,
                     "content": content, **kwargs},
            room=self.room,
        )

    def _publish_event(self, payload):
        frappe.publish_realtime(
            event="agent_event",
            message=payload,
            room=self.room,
        )