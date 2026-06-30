# omnis_hermes/agent/conversation.py
import json
import frappe
from frappe.realtime import get_user_room

SESSION_DOCTYPE = "Agent session"

class Conversation:
    def __init__(self, session_id=None, user=None):
        # CRITICAL: Fall back to session.user ONLY if not in a background job
        self.user = user or frappe.session.user or "Guest"

        # FIX: use Frappe's own room-naming helper instead of a hand-rolled
        # f"user_{user}" string. The frontend socket client auto-joins
        # whatever get_user_room() returns on connect — if we publish to a
        # different string, events vanish silently with no error.
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

    def get_messages(self):
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        for row in self.doc.messages:
            msg = {"role": row.role, "content": row.content or ""}
            if row.role == "assistant" and row.tool_calls:
                msg["tool_calls"] = frappe.parse_json(row.tool_calls)
            elif row.role == "tool":
                msg["tool_call_id"] = row.tool_call_id
                msg["name"] = row.tool_name
            messages.append(msg)
        return messages

    def set_system(self, text):
        self.system_prompt = text

    def add_user_message(self, text):
        if not self.doc.title:
            self.doc.title = text[:72]
        self.doc.append("messages", {"role": "user", "content": text})
        self._emit("user", text)

    def add_assistant_message(self, message_obj, streamed=False):
        content = message_obj.get("content") or ""
        tool_calls = message_obj.get("tool_calls")

        self.doc.append("messages", {
            "role": "assistant",
            "content": content,
            "tool_calls": frappe.as_json(tool_calls) if tool_calls else None,
        })
        # FIX: when this turn was streamed, the frontend already built up
        # `content` token-by-token via emit_token(). Re-emitting the full
        # text here would duplicate the bubble. Only emit for non-streamed
        # turns (e.g. a fallback path, or tests that call this directly).
        if content and not streamed:
            self._emit("assistant", content)

    def emit_token(self, delta):
        """Called per text fragment during a streamed turn."""
        if not delta:
            return
        frappe.publish_realtime(
            event="agent_token",
            message={"session_id": self.session_id, "delta": delta},
            room=self.room
        )

    def emit_tool_start(self, tool_call_id, tool_name, args):
        self._publish_event({
            "type": "tool_start",
            "tool": tool_name,
            "args": json.dumps(args) if isinstance(args, dict) else str(args),
            "call_id": tool_call_id
        })

    def add_tool_result(self, tool_call_id, name, content, elapsed_ms=None):
        self.doc.append("messages", {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "tool_name": name,
            "content": content
        })

        payload = {
            "type": "tool_done",
            "tool": name,
            "call_id": tool_call_id,
        }

        if isinstance(content, str) and content.startswith("Error:"):
            payload["error"] = content[:500]
        else:
            payload["result"] = str(content)[:500]

        if elapsed_ms is not None:
            payload["elapsed_ms"] = elapsed_ms

        self._publish_event(payload)

    def emit_done(self, response):
        """FIX: terminal event so the frontend knows the turn is complete
        and can close out the action-steps timeline / unlock input."""
        frappe.publish_realtime(
            event="agent_done",
            message={"session_id": self.session_id, "response": response},
            room=self.room
        )

    def emit_error(self, error_text):
        frappe.publish_realtime(
            event="agent_error",
            message={"session_id": self.session_id, "response": error_text},
            room=self.room
        )

    def save(self):
        self.doc.save(ignore_permissions=True)
        # FIX: background workers don't auto-commit at job end the way a
        # request context does. Without this, messages saved here can be
        # lost if the worker process exits before the queue's own commit,
        # and reads from another request may not see them yet.
        frappe.db.commit()

    # ── Private Emit Helpers ──────────────────────────────────

    def _emit(self, role, content, **kwargs):
        if not content:
            return
        frappe.publish_realtime(
            event="agent_message",
            message={"session_id": self.session_id, "role": role, "content": content, **kwargs},
            room=self.room  # EXPLICIT ROOM TARGETING (now via get_user_room)
        )

    def _publish_event(self, payload):
        frappe.publish_realtime(
            event="agent_event",
            message=payload,
            room=self.room  # EXPLICIT ROOM TARGETING (now via get_user_room)
        )