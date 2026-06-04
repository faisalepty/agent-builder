import json
import frappe
import threading
from frappe.utils import now_datetime
from frappe.realtime import emit_via_redis, get_user_room
from run_agent import AIAgent


@frappe.whitelist()
def new_chat(title=None, message=None):
    """Create a new Agent Chat and return its name."""
    user = frappe.session.user
    doc = frappe.get_doc({
        "doctype": "Agent Chat",
        "title": title or message[:50] if message else "New Chat",
        "user": user,
        "status": "Active",
        "last_active": now_datetime(),
        "message_count": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"chat_id": doc.name, "title": doc.title}


@frappe.whitelist()
def get_messages(chat_id, limit=50, start=0):
    """Load display messages for a chat — paginated."""
    # Verify ownership
    chat = frappe.get_doc("Agent Chat", chat_id)
    if chat.user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    messages = frappe.get_list(
        "Agent Chat Message",
        filters={"chat": chat_id},
        fields=["name", "role", "content", "timestamp"],
        order_by="timestamp asc",
        limit=limit,
        start=start,
    )
    return {"messages": messages, "title": chat.title}


@frappe.whitelist()
def get_chats():
    """Return the current user's chat list."""
    user = frappe.session.user
    chats = frappe.get_list(
        "Agent Chat",
        filters={"user": user, "status": "Active"},
        fields=["name", "title", "last_active", "message_count"],
        order_by="last_active desc",
        limit=50,
    )
    return {"chats": chats}


@frappe.whitelist()
def chat(message, chat_id=None):
    """Send a message. Creates a new chat if chat_id is not provided."""
    user = frappe.session.user
    site = frappe.local.site
    room = get_user_room(user)

    # Create a new chat inline if none provided
    if not chat_id:
        result = new_chat(message=message)
        chat_id = result["chat_id"]

    # Verify ownership before doing anything
    chat_doc = frappe.get_doc("Agent Chat", chat_id)
    if chat_doc.user != user:
        frappe.throw("Not authorised", frappe.PermissionError)

    # Load compressed context for the agent
    agent_context = None
    if chat_doc.agent_context:
        try:
            agent_context = json.loads(chat_doc.agent_context)
        except Exception:
            agent_context = None

    def publish(event, data):
        emit_via_redis(event, data, room)

    def on_token(delta):
        publish("agent_token", {"delta": delta})

    def on_tool_start(tool_call_id, tool_name, args):
        publish("agent_event", {
            "type": "tool_start",
            "tool": tool_name,
            "args": json.dumps(args),
            "call_id": tool_call_id
        })

    def on_tool_done(tool_call_id, tool_name, args, result):
        publish("agent_event", {
            "type": "tool_done",
            "tool": tool_name,
            "result": str(result)[:500],
            "call_id": tool_call_id
        })

    def on_tool_status(event_type, tool_name=None, preview=None, **kwargs):
        payload = {"type": "tool_progress", "event": event_type}
        if tool_name:
            payload["tool"] = tool_name
        if preview:
            payload["preview"] = preview
        publish("agent_event", payload)

    def run():
        frappe.init(site=site)
        frappe.connect()
        try:
            # 1 — Save user message to display history
            frappe.get_doc({
                "doctype": "Agent Chat Message",
                "chat": chat_id,
                "role": "user",
                "content": message,
                "timestamp": now_datetime(),
            }).insert(ignore_permissions=True)

            # 2 — Run agent with compressed context
            agent = AIAgent(
                model="openai/gpt-oss-120b:free",
                quiet_mode=False,
                platform="frappe",
                enabled_toolsets=["frappe_tools"],
                stream_delta_callback=on_token,
                tool_start_callback=on_tool_start,
                tool_complete_callback=on_tool_done,
                tool_progress_callback=on_tool_status,
            )
            result = agent.run_conversation(
                user_message=message,
                conversation_history=agent_context,
            )

            final_response = result["final_response"]

            # 3 — Save assistant message to display history
            frappe.get_doc({
                "doctype": "Agent Chat Message",
                "chat": chat_id,
                "role": "assistant",
                "content": final_response,
                "timestamp": now_datetime(),
            }).insert(ignore_permissions=True)

            # 4 — Overwrite compressed context and update metadata
            frappe.db.set_value("Agent Chat", chat_id, {
                "agent_context": json.dumps(result["messages"], default=str),
                "last_active": now_datetime(),
                "message_count": (chat_doc.message_count or 0) + 2,
            })
            frappe.db.commit()

            publish("agent_done", {
                "response": final_response,
                "chat_id": chat_id,
            })

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Agent Chat Error")
            publish("agent_done", {"response": f"Error: {str(e)}", "chat_id": chat_id})
        finally:
            frappe.destroy()

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "chat_id": chat_id}