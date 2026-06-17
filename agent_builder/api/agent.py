import json
import re
import frappe
import threading
import os
from pathlib import Path
from frappe.utils import now_datetime
from frappe.realtime import emit_via_redis, get_user_room



def setup_environment():
    """Set up necessary environment variables for the Hermes Agent framework."""
    os.environ["HERMES_HOME"] = str(Path(__file__).resolve().parent.parent.parent / ".hermes")
    os.environ["HERMES_ENABLE_PROJECT_PLUGINS"] = "true"

    print(f"\n \n \n HERMES_HOME: {os.environ['HERMES_HOME']}")

    # 1. Fetch the document instance
    agent_setup = frappe.get_doc("Agent Setup")
    
    # 2. Extract the decrypted plain-text password safely
    openrouter_key = agent_setup.get_password("openrouter_api_key")
    
    if openrouter_key:
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
    else:
        frappe.throw("OpenRouter API key not set in Agent Setup", frappe.ValidationError)


@frappe.whitelist()
def new_chat(title=None, message=None):
    """Create a new Agent Chat and return its name."""
    # if message == "":
    #     return {"chat_id": None, "title": "New Chat"}
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
        # If you add an `attachments` (Long Text/JSON) field to "Agent Chat
        # Message", include it here, e.g. fields=[..., "attachments"], so
        # loadHistory() in chat_messages.js can show attachment chips again
        # on reload.
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


def _slugify(value):
    """Turn a skill's display name into a clean /slash-command token."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")

def _list_skills_for_frontend():
    """
    Returns [{"name": <slug used after '/'>, "label": <display name>, "description": <tooltip text>}, ...]

    Natively hooks into the Hermes Agent framework's skills_tool component 
    and handles its structural response payload.
    """
    try:
        try:
            from tools.skills_tool import skills_list
        except ImportError:
            # Alternate package lookup orientation path
            from hermes.tools.skills_tool import skills_list

        response = skills_list()
        print(f"get_skills: Raw Hermes skills_tool response: {response}")
        # If the response is a raw JSON string, parse it into a Python object
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except Exception as json_err:
                frappe.log_error(frappe.get_traceback(), f"get_skills: Failed to parse raw JSON string response. Error: {str(json_err)}")

        # Extract the target array from the Hermes structured dictionary payload
        native_skills = []
        if isinstance(response, dict) and "skills" in response:
            native_skills = response["skills"]
        elif isinstance(response, list):
            # Defensive fallback if format changes upstream
            native_skills = response

        if native_skills:
            skills = []
            for s in native_skills:
                name = s.get("name") or ""
                description = s.get("description") or ""
                
                # Transform standardized slugs to clean UI display text
                # e.g., 'fin-audit-support' -> 'Fin Audit Support'
                label = name.replace("-", " ").title()
                
                # Special handling for common UI acronym preservation
                if label.endswith(" Ui"):
                    label = label[:-3] + " UI"
                
                skills.append({
                    "name": _slugify(name),
                    "label": label,
                    "description": description,
                })
            return skills
                
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), 
            f"get_skills: Native Hermes skills_tool extraction failed. Error: {str(e)}"
        )

    return []


@frappe.whitelist()
def get_skills():
    """Return all skills available to the agent, for the chat UI's '+' / '/' picker."""
    return {"skills": _list_skills_for_frontend()}

@frappe.whitelist()
def chat(message, chat_id=None, attachments=None):
    """Send a message. Creates a new chat if chat_id is not provided.

    `attachments` is an optional JSON string of already-uploaded files:
        [{"file_name": "invoice.pdf", "file_url": "/files/invoice.pdf"}, ...]
    """
    user = frappe.session.user
    site = frappe.local.site
    room = get_user_room(user)
    setup_environment()
    from run_agent import AIAgent

    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments) if attachments else []
        except Exception:
            attachments = []
    attachments = attachments or []

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

    # Fold attachment references into what the agent actually receives, so it
    # knows the files exist even though no dedicated attachment handling has
    # been wired into AIAgent yet.
    agent_message = message
    if attachments:
        file_lines = "\n".join(
            f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}" for a in attachments
        )
        agent_message = f"{message}\n\n[Attached files]\n{file_lines}".strip()

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
            user_msg_doc = {
                "doctype": "Agent Chat Message",
                "chat": chat_id,
                "role": "user",
                "content": message,
                "timestamp": now_datetime(),
            }
            if attachments:
                # Best-effort persistence: this key is only saved if "Agent Chat
                # Message" actually has an `attachments` field (e.g. Long Text /
                # JSON). If it doesn't, Frappe just ignores the unknown attribute
                # on insert rather than erroring — but history reloads won't show
                # attachment chips again until that field is added. Add it to get
                # full persistence across reloads.
                user_msg_doc["attachments"] = json.dumps(attachments)
            frappe.get_doc(user_msg_doc).insert(ignore_permissions=True)

            # 2 — Run agent with compressed context
            agent = AIAgent(
                model="openrouter/owl-alpha",
                quiet_mode=False,
                platform="frappe",
                enabled_toolsets=["frappe_tools","clarify","delegetion", "skills", "memory", "todo", "search", "session-search"],
                stream_delta_callback=on_token,
                tool_start_callback=on_tool_start,
                tool_complete_callback=on_tool_done,
                tool_progress_callback=on_tool_status,
            )
            result = agent.run_conversation(
                user_message=agent_message,
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