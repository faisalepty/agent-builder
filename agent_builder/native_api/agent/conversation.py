# omnis_hermes/agent/conversation.py
import json

import frappe
from frappe.utils import now_datetime
from frappe.realtime import get_user_room

SESSION_DOCTYPE = "Agent session"

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
        self.doc.append("messages", {
            "role": "user",
            "content": text,
            "timestamp": now_datetime(),
        })
        self._emit("user", text)

    def add_assistant_message(self, message_obj, streamed=False):
        content = message_obj.get("content") or ""
        tool_calls = message_obj.get("tool_calls")

        self.doc.append("messages", {
            "role": "assistant",
            "content": content,
            "tool_calls": frappe.as_json(tool_calls) if tool_calls else None,
            "timestamp": now_datetime(),
        })
        if content and not streamed:
            self._emit("assistant", content)

    def emit_token(self, delta):
        if not delta:
            return
        frappe.publish_realtime(
            event="agent_token",
            message={"session_id": self.session_id, "delta": delta},
            room=self.room
        )

    def emit_reasoning(self, delta):
        if not delta:
            return
        frappe.publish_realtime(
            event="agent_reasoning",
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
            "content": content,
            "timestamp": now_datetime(),
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
        self.doc.last_active = now_datetime()
        self.doc.message_count = len(self.doc.messages)
        self.doc.save(ignore_permissions=True)
        frappe.db.commit()

    # ── Private Emit Helpers ──────────────────────────────────

    def _emit(self, role, content, **kwargs):
        if not content:
            return
        frappe.publish_realtime(
            event="agent_message",
            message={"session_id": self.session_id, "role": role, "content": content, **kwargs},
            room=self.room
        )

    def _publish_event(self, payload):
        frappe.publish_realtime(
            event="agent_event",
            message=payload,
            room=self.room
        )
