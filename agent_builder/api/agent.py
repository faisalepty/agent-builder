import json
import re
import os
import time
import threading
from pathlib import Path
import frappe
from frappe.utils import now_datetime
from frappe.realtime import emit_via_redis, get_user_room


def setup_environment():
    """Set up necessary environment variables for the Hermes Agent framework."""
    os.environ["HERMES_HOME"] = str(Path(__file__).resolve().parent.parent.parent / ".hermes")
    os.environ["HERMES_ENABLE_PROJECT_PLUGINS"] = "true"

    agent_setup = frappe.get_doc("Agent Setup")
    openrouter_key = agent_setup.get_password("openrouter_api_key")
    
    if not openrouter_key:
        frappe.throw("OpenRouter API key not set in Agent Setup", frappe.ValidationError)
    
    os.environ["OPENROUTER_API_KEY"] = openrouter_key

setup_environment()
from run_agent import AIAgent

@frappe.whitelist()
def new_chat(title=None, message=None):
    """Create a new Agent Chat and return its name."""
    doc = frappe.get_doc({
        "doctype": "Agent Chat",
        "title": title or (message[:50] if message else "New Chat"),
        "user": frappe.session.user,
        "status": "Active",
        "last_active": now_datetime(),
        "message_count": 0,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    
    return {"chat_id": doc.name, "title": doc.title}

@frappe.whitelist()
def get_messages(chat_id, limit=50, start=0):
    """Load display messages for a chat — paginated."""
    chat = frappe.get_doc("Agent Chat", chat_id)
    if chat.user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    base_fields = ["name", "role", "content", "timestamp"]
    extra_fields = ["attachments", "tool_calls", "is_error"]
    
    query_kwargs = {
        "doctype": "Agent Chat Message",
        "filters": {"chat": chat_id},
        "order_by": "timestamp asc",
        "limit": limit,
        "start": start,
    }

    try:
        messages = frappe.get_list(fields=base_fields + extra_fields, **query_kwargs)
    except Exception:
        # Fallback if extra fields haven't been added to the DocType yet
        messages = frappe.get_list(fields=base_fields, **query_kwargs)
        
    return {"messages": messages, "title": chat.title}

@frappe.whitelist()
def get_chats():
    """Return the current user's chat list."""
    chats = frappe.get_list(
        "Agent Chat",
        filters={"user": frappe.session.user, "status": "Active"},
        fields=["name", "title", "last_active", "message_count"],
        order_by="last_active desc",
        limit=50,
    )
    return {"chats": chats}

def _slugify(value):
    """Turn a skill's display name into a clean /slash-command token."""
    value = (value or "").strip().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-")

def _list_skills_for_frontend():
    """Returns frontend-formatted skills payload natively from Hermes."""
    try:
        try:
            from tools.skills_tool import skills_list
        except ImportError:
            from hermes.tools.skills_tool import skills_list

        response = skills_list()
        
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), f"get_skills JSON parse error: {e}")
                return []

        native_skills = response.get("skills", []) if isinstance(response, dict) else (response if isinstance(response, list) else [])

        return [
            {
                "name": _slugify(s.get("name")),
                "label": (s.get("name") or "").replace("-", " ").title().replace(" Ui", " UI"),
                "description": s.get("description") or "",
            }
            for s in native_skills
        ]
                
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"get_skills extraction failed: {e}")
        return []

@frappe.whitelist()
def get_skills():
    """Return all skills available to the agent."""
    return {"skills": _list_skills_for_frontend()}

@frappe.whitelist()
def chat(message, chat_id=None, attachments=None):
    """Send a message. Creates a new chat if chat_id is not provided."""
    user = frappe.session.user
    site = frappe.local.site
    room = get_user_room(user)

    # Clean up attachment parsing
    if isinstance(attachments, str):
        try:
            attachments = json.loads(attachments)
        except Exception:
            attachments = []
    attachments = attachments or []

    if not chat_id:
        chat_id = new_chat(message=message)["chat_id"]

    chat_doc = frappe.get_doc("Agent Chat", chat_id)
    if chat_doc.user != user:
        frappe.throw("Not authorised", frappe.PermissionError)

    # Safe context parsing
    agent_context = None
    if chat_doc.agent_context:
        try:
            agent_context = json.loads(chat_doc.agent_context)
        except Exception:
            pass

    # Fold attachment references into the message for the agent
    agent_message = message
    if attachments:
        file_lines = "\n".join(f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}" for a in attachments)
        agent_message = f"{message}\n\n[Attached files]\n{file_lines}".strip()

    def publish(event, data):
        emit_via_redis(event, data, room)

    tool_call_log = []
    _tool_start_times = {}

    def on_token(delta):
        publish("agent_token", {"delta": delta})

    def on_tool_start(tool_call_id, tool_name, args):
        publish("agent_event", {"type": "tool_start", "tool": tool_name, "args": json.dumps(args), "call_id": tool_call_id})
        _tool_start_times[tool_call_id] = time.time()
        tool_call_log.append({
            "call_id": tool_call_id,
            "tool": tool_name,
            "args": json.dumps(args) if not isinstance(args, str) else args,
            "status": "running",
        })

    def on_tool_done(tool_call_id, tool_name, args, result):
        publish("agent_event", {"type": "tool_done", "tool": tool_name, "result": str(result)[:500], "call_id": tool_call_id})
        started = _tool_start_times.pop(tool_call_id, None)
        for entry in tool_call_log:
            if entry.get("call_id") == tool_call_id:
                entry["status"] = "done"
                entry["elapsed_ms"] = int((time.time() - started) * 1000) if started else None
                break

    def on_tool_status(event_type, tool_name=None, preview=None, **kwargs):
        payload = {"type": "tool_progress", "event": event_type}
        if tool_name: payload["tool"] = tool_name
        if preview: payload["preview"] = preview
        publish("agent_event", payload)

    def run():
        frappe.init(site=site)
        frappe.connect()
        
        # DRY Helper for saving message history
        def save_chat_message(role, content, extra_fields=None):
            doc = {
                "doctype": "Agent Chat Message",
                "chat": chat_id,
                "role": role,
                "content": content,
                "timestamp": now_datetime(),
            }
            if extra_fields:
                doc.update(extra_fields)
            frappe.get_doc(doc).insert(ignore_permissions=True)

        try:
            # 1. Save user message
            user_extras = {"attachments": json.dumps(attachments)} if attachments else {}
            save_chat_message("user", message, user_extras)

            # 2. Run agent
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
            result = agent.run_conversation(user_message=agent_message, conversation_history=agent_context)
            final_response = result["final_response"]

            # 3. Save assistant message
            assistant_extras = {"tool_calls": json.dumps(tool_call_log)} if tool_call_log else {}
            save_chat_message("assistant", final_response, assistant_extras)

            # 4. Overwrite compressed context and update metadata
            frappe.db.set_value("Agent Chat", chat_id, {
                "agent_context": json.dumps(result["messages"], default=str),
                "last_active": now_datetime(),
                "message_count": (chat_doc.message_count or 0) + 2,
            })
            frappe.db.commit()

            publish("agent_done", {"response": final_response, "chat_id": chat_id})

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Agent Chat Error")

            for entry in tool_call_log:
                if entry.get("status") == "running":
                    entry["status"] = "interrupted"

            error_text = f"Sorry, something went wrong: {e}" if frappe.conf.get("developer_mode") else "Sorry, something went wrong while processing that request. Please try again."

            try:
                error_extras = {"is_error": 1}
                if tool_call_log: error_extras["tool_calls"] = json.dumps(tool_call_log)
                save_chat_message("assistant", error_text, error_extras)
                frappe.db.commit()
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Agent Chat Error - failed to save failure message")

            try:
                publish("agent_error", {"response": error_text, "chat_id": chat_id})
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Agent Chat Error - failed to publish failure event")
        finally:
            frappe.destroy()

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "chat_id": chat_id}