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

    def get_messages(self, reasoning_replay=None):
        """Rebuild the OpenAI-style message list from the two normalized tables.

        reasoning_replay: optional callable(meta, had_tool_calls, msg) — see
        OpenAIProvider.replay_reasoning. When given, it decides how (or
        whether) each assistant row's stored reasoning_meta gets reattached
        to the outgoing message for this specific provider/model. When
        omitted, falls back to the old universal behavior of merging
        buffered plain-text reasoning into a <think> block inside content —
        safe for simple open-weight deployments, but NOT correct for
        providers with strict replay requirements (DeepSeek V4, OpenRouter
        reasoning models with tool calls). Always pass the provider's bound
        replay_reasoning when one is available.
        """
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Index tool calls by their parent message_id, preserving insertion order.
        tool_calls_by_parent: dict[str, list] = {}
        for tc in self.doc.tool_calls:
            tool_calls_by_parent.setdefault(tc.parent_message, []).append(tc)

        # Buffer to accumulate reasoning so we can attach it to the next
        # assistant turn — only used in the no-strategy fallback path.
        pending_reasoning = []

        for row in self.doc.messages:
            if row.role == "reasoning":
                if reasoning_replay is None and row.content:
                    pending_reasoning.append(row.content.strip())
                continue

            if row.role == "assistant":
                content = row.content or ""
                tc_rows = tool_calls_by_parent.get(row.message_id, [])
                had_tool_calls = bool(tc_rows)

                if reasoning_replay is None:
                    # Fallback: re-attach preceding reasoning into the
                    # assistant's content block as a <think> tag. Fine for
                    # providers that just want text; not correct for
                    # providers with structural replay requirements.
                    if pending_reasoning:
                        reasoning_text = "\n\n".join(pending_reasoning)
                        if content:
                            content = f"<think>\n{reasoning_text}\n</think>\n\n{content}"
                        else:
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

                if reasoning_replay is not None:
                    reasoning_meta = None
                    stored = getattr(row, "reasoning_meta", None)
                    if stored:
                        try:
                            reasoning_meta = json.loads(stored)
                        except (TypeError, ValueError):
                            reasoning_meta = None
                    reasoning_replay(reasoning_meta, had_tool_calls, msg)

                # OpenAI's Chat Completions API strictly requires that every
                # tool_call_id in an assistant message be immediately followed
                # by a matching tool-role reply — with NO exceptions, unlike
                # OpenRouter/NVIDIA which tolerate gaps. If a tool call got
                # stuck in "pending"/"running" (crash, restart, interrupted
                # turn) and never resolved, we must still emit a synthetic
                # tool reply for it, or every subsequent request to OpenAI
                # will 400 with "did not have response messages: call_xxx".
                for tc in tc_rows:
                    if tc.status in ("success", "error"):
                        result_content = (tc.error if tc.status == "error"
                                          else tc.result) or ""
                    else:
                        result_content = (
                            "Error: tool execution was interrupted and no "
                            "result was recorded."
                        )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "name": tc.tool_name,
                        "content": result_content,
                    })
            else:
                # For User or System messages, clear reasoning buffer if out of order
                pending_reasoning = []
                messages.append({"role": row.role, "content": row.content or ""})

        return messages

    # ── Mutators ─────────────────────────────────────────

    def set_system(self, text):
        self.system_prompt = text

    def add_system_message(self, text):
        """Append a system-scoped message at this point in the conversation.

        Unlike set_system() — which sets the global session-level prompt that
        gets prepended as the very first message — this inserts a system
        message inline, right before the next user/assistant message.

        Used for per-turn skill injections: when a user types /skill-name,
        the skill's content is loaded and inserted here so the agent sees
        it as contextual instructions scoped to that specific request.
        """
        msg_id = _gen_id()
        self.doc.append("messages", {
            "message_id": msg_id,
            "role": "system",
            "content": text,
            "timestamp": now_datetime(),
        })
        self._last_message_id = msg_id

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

    def add_assistant_message(self, message_obj, streamed=False, latency_ms=None):
        self._flush_reasoning()

        content = message_obj.get("content") or ""
        tool_calls = message_obj.get("tool_calls") or []
        reasoning_meta = message_obj.get("reasoning_meta")
        reasoning_text = message_obj.get("reasoning")
        # Populated by OpenAIProvider.generate() — see openai_api.py. Handles
        # both Chat Completions (prompt_tokens/completion_tokens) and
        # Anthropic/Responses-style (input_tokens/output_tokens) usage shapes
        # so this layer stays provider-agnostic.
        usage = message_obj.get("usage") or {}
        model = message_obj.get("model")
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

        self._turn_index = getattr(self, "_turn_index", 0) + 1

        # If this call wasn't streamed, reasoning text never went through
        # emit_reasoning()/_flush_reasoning() above, so it would otherwise
        # be silently dropped. Persist it now as its own reasoning-role row
        # so UI/timeline reconstruction still works for non-streamed turns.
        if reasoning_text and not streamed:
            self.doc.append("messages", {
                "message_id": _gen_id(),
                "role": "reasoning",
                "content": reasoning_text,
                "timestamp": now_datetime(),
            })

        msg_id = _gen_id()
        self.doc.append("messages", {
            "message_id": msg_id,
            "role": "assistant",
            "content": content,
            "is_error": bool(message_obj.get("is_error")),
            # Raw, provider-specific reasoning payload (reasoning_details,
            # signatures, etc.) — kept verbatim so it can be replayed back
            # correctly later. Requires a "reasoning_meta" Long Text/JSON
            # field on the Agent Message child table.
            "reasoning_meta": json.dumps(reasoning_meta) if reasoning_meta else None,
            "turn_index": self._turn_index,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "reasoning_tokens": reasoning_tokens,
            "latency_ms": latency_ms,
            "timestamp": now_datetime(),
        })
        self._last_message_id = msg_id

        # Denormalize onto the session doc for cheap dashboard queries —
        # avoids a child-table aggregation just to plot cost/turns per session.
        if model and not self.doc.model:
            self.doc.model = model
        self.doc.total_input_tokens = (self.doc.total_input_tokens or 0) + input_tokens
        self.doc.total_output_tokens = (self.doc.total_output_tokens or 0) + output_tokens
        self.doc.turn_count = self._turn_index

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

    def add_tool_result(self, tool_call_id, name, content, elapsed_ms=None, was_loop_strike=False):
        is_error = isinstance(content, str) and content.startswith("Error:")
        now = now_datetime()

        for tc in self.doc.tool_calls:
            if tc.call_id != tool_call_id:
                continue

            tc.status = "error" if is_error else "success"
            tc.completed_at = now
            tc.was_loop_strike = was_loop_strike

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

    def save(self, ended_reason=None):
        self._flush_reasoning()
        self.doc.last_active = now_datetime()
        self.doc.message_count = len(self.doc.messages)
        self.doc.tool_call_count = len(self.doc.tool_calls)
        if ended_reason:
            self.doc.ended_reason = ended_reason
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