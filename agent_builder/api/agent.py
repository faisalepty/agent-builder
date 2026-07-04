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
    """Set up necessary environment variables and Hermes config from Agent Setup."""
    hermes_home = Path(__file__).resolve().parent.parent.parent / ".hermes"
    os.environ["HERMES_HOME"] = str(hermes_home)
    os.environ["HERMES_ENABLE_PROJECT_PLUGINS"] = "true"

    agent_setup = frappe.get_doc("Agent Setup")
    api_key = agent_setup.get_password("api_key")
    provider = (agent_setup.provider or "openrouter").strip().lower()
    model = (agent_setup.model or "").strip()

    if not api_key:
        frappe.throw("API key not set in Agent Setup", frappe.ValidationError)

    # Provider name mapping: Agent Setup uses friendly names, Hermes uses internal IDs.
    # "openai" in Hermes is aliased to openrouter — direct OpenAI API access needs "openai-api".
    _provider_hermes_id = {
        "openai":      "openai-api",   # direct api.openai.com — env var: OPENAI_API_KEY
        "openrouter":  "openrouter",   # env var: OPENROUTER_API_KEY
        "anthropic":   "anthropic",    # env var: ANTHROPIC_API_KEY
        "gemini":      "gemini",       # env var: GEMINI_API_KEY
    }
    hermes_provider = _provider_hermes_id.get(provider, provider)

    # Set the provider's env var (e.g. OPENAI_API_KEY, OPENROUTER_API_KEY)
    os.environ[provider.upper() + "_API_KEY"] = api_key

    # Default model per provider when none is specified
    _provider_defaults = {
        "openai":      "gpt-4o-mini",
        "openrouter":  "anthropic/claude-sonnet-4",
        "anthropic":   "claude-3-5-sonnet-latest",
        "gemini":      "gemini-2.5-pro",
    }
    effective_model = model or _provider_defaults.get(provider, "gpt-4o-mini")

    # Write Hermes config.yaml so the framework picks up the right provider/model
    config_path = hermes_home / "config.yaml"
    try:
        import yaml as _yaml
        # Read existing config to preserve other keys (e.g. plugins)
        if config_path.exists():
            with open(config_path, "r") as f:
                config = _yaml.safe_load(f) or {}
        else:
            config = {}

        config["model"] = {
            "provider": hermes_provider,
            "default":  effective_model,
        }

        with open(config_path, "w") as f:
            _yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    except Exception as e:
        frappe.log_error(title="Hermes Config Write Failed", message=str(e))
   

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
    if not value:
        return ""
   
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")

def build_skills_system_prompt() -> str:
    """
    Build the <available_skills> block for the agent system prompt.
    Similar to Hermes' build_skills_system_prompt().
    """

    skills = frappe.get_all(
        "Skill",
        fields=[
            "name_",
            "description"
        ],
        order_by="name_ asc"
    )

    lines = []
    
    # Add operation guardrails first
    lines.append("<operation_guardrails>")
    lines.append("CRITICAL RESTRICTIONS - You MUST follow these rules:")
    lines.append("")
    lines.append("1. DELETION: You are NOT capable of deleting records from the system.")
    lines.append("   The delete functionality has been intentionally removed.")
    lines.append("   When a user asks to delete a record:")
    lines.append("   - Explain that you cannot delete records")
    lines.append("   - List the available alternatives the USER can do themselves:")
    lines.append("     * Cancel it (if the DocType supports cancellation)")
    lines.append("     * Mark it as disabled (if the DocType has a 'disabled' field)")
    lines.append("     * Update its status to inactive (if the DocType has a status field)")
    lines.append("   - DO NOT perform any of these alternatives yourself")
    lines.append("   - DO NOT call frappe_save_doc to set disabled=1 or status='Disabled'")
    lines.append("   - ONLY explain what options are available for that particular document type")
    lines.append("")
    lines.append("2. DISABLING/INACTIVATING: When a user asks to disable or set a record to inactive:")
    lines.append("   - DO NOT automatically perform the action")
    lines.append("   - Instead, explain to the user how they can do it themselves:")
    lines.append("     * Which field to update (e.g., 'disabled' checkbox)")
    lines.append("     * Where to find it in the UI")
    lines.append("   - ONLY perform the action if the user EXPLICITLY confirms after your explanation")
    lines.append("")
    lines.append("3. WORKAROUNDS: Never attempt workarounds for restricted operations.")
    lines.append("   If you cannot perform an action directly, explain alternatives but DO NOT execute them.")
    lines.append("")
    lines.append("</operation_guardrails>")
    lines.append("")

    if skills:
        lines.append("<available_skills>")

        for skill in skills:
            name = skill.get("name_")
            description = skill.get("description", "")

            if not name:
                continue

            lines.append(f"- {name}: {description}")

        lines.append("</available_skills>")
        lines.append("")
        lines.append(
            "Before replying, review the available skills above. "
            "If one or more skills appear relevant to the user's request, "
            "call skill_view(skill_name) to load the full instructions before proceeding. "
            "Skills contain workflows, conventions, implementation patterns, "
            "and quality standards specific to this Frappe environment. "
            "Do not assume skill contents; load the skill first when needed."
        )

    return "\n".join(lines)

@frappe.whitelist(allow_guest=False)
def check_chat_access():
    """
    Returns whether the current user is allowed to use the chat widget.
    If 'allowed_role' is set in Agent Setup, only users with that role can access it.
    If blank, all logged-in users can access it.
    """
    try:
        agent_setup = frappe.get_doc("Agent Setup")
        allowed_role = agent_setup.get("allowed_role")

        if not allowed_role:
            # No restriction configured — everyone has access
            return {"has_access": True}

        user_roles = frappe.get_roles(frappe.session.user)
        has_access = allowed_role in user_roles
        return {"has_access": has_access, "required_role": allowed_role}

    except Exception:
        frappe.log_error(title="Chat Access Check Failed", message=frappe.get_traceback())
        # Fail open — don't hide the chat if Agent Setup can't be read
        return {"has_access": True}


@frappe.whitelist()
def get_skills():
    """Return all skills available to the agent for the frontend."""

    try:
        native_skills = frappe.get_all(
            "Skill",
            fields=[
                "name_",
                "description"
            ],
            order_by="name_ asc"
        )

        formatted_skills = []

        for s in native_skills:
            raw_name = s.get("name_")

            if not raw_name:
                continue

            formatted_skills.append({
                "name": _slugify(raw_name),
                "label": raw_name.replace("-", " ").title().replace(" Ui", " UI"),
                "description": s.get("description", "")
            })

        return {"skills": formatted_skills}

    except Exception:
        frappe.log_error(
            title="Skills Extraction Failed",
            message=frappe.get_traceback()
        )
        return {"skills": []}

def parse_json(data, default=None):
    """Safely parse JSON strings, returning a default if parsing fails."""
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return default if default is not None else []
    return data or (default if default is not None else [])


# --- 2. The API Endpoint ---
@frappe.whitelist()
def chat(message, chat_id=None, attachments=None):
    """Queue a message to be sent to the AI agent."""
    user = frappe.session.user
    attachments = parse_json(attachments, [])

    if not chat_id:
        chat_id = new_chat(message=message).get("chat_id")

    chat_doc = frappe.get_doc("Agent Chat", chat_id)
    if chat_doc.user != user:
        frappe.throw("Not authorized", frappe.PermissionError)

    frappe.enqueue(
        method="agent_builder.api.agent.process_agent_chat",  
        queue="short",
        timeout=300,
        now=frappe.flags.in_test,
        message=message,
        chat_id=chat_id,
        attachments=attachments,
        user=user
    )

    return {"status": "queued", "chat_id": chat_id}


# --- 3. The Background Task ---
def process_agent_chat(message, chat_id, attachments, user):
    """Background job to process the AI agent interaction."""

    # Re-run setup on every request so provider/model/key changes in Agent Setup
    # are picked up immediately without restarting workers.
    setup_environment()

    chat_doc = frappe.get_doc("Agent Chat", chat_id)
    room = get_user_room(user)
    agent_context = parse_json(chat_doc.agent_context, None)

    agent_message = message
    if attachments:
        file_lines = "\n".join(
            f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}"
            for a in attachments
        )
        agent_message = f"{message}\n\n[Attached files]\n{file_lines}".strip()

    def publish(event, data):
        frappe.publish_realtime(event, data, room=room)

    tool_call_log = []
    _tool_start_times = {}

    def on_token(delta):
        publish("agent_token", {"delta": delta})

    def on_tool_start(tool_call_id, tool_name, args):
        publish("agent_event", {
            "type": "tool_start", "tool": tool_name,
            "args": json.dumps(args), "call_id": tool_call_id
        })
        _tool_start_times[tool_call_id] = time.time()
        tool_call_log.append({
            "call_id": tool_call_id, "tool": tool_name,
            "args": json.dumps(args) if not isinstance(args, str) else args,
            "status": "running",
        })

    def on_tool_done(tool_call_id, tool_name, args, result):
        publish("agent_event", {
            "type": "tool_done", "tool": tool_name,
            "result": str(result)[:500], "call_id": tool_call_id
        })
        started = _tool_start_times.pop(tool_call_id, None)
        for entry in tool_call_log:
            if entry.get("call_id") == tool_call_id:
                entry.update({
                    "status": "done",
                    "elapsed_ms": int((time.time() - started) * 1000) if started else None
                })
                break

    def on_tool_status(event_type, tool_name=None, preview=None, **kwargs):
        payload = {"type": "tool_progress", "event": event_type}
        if tool_name:
            payload["tool"] = tool_name
        if preview:
            payload["preview"] = preview
        publish("agent_event", payload)

    def save_chat_message(role, content, extra_fields=None):
        # Guard: content is mandatory in the doctype — use a fallback for
        # tool-only turns where the LLM returns no text.
        if not content or not str(content).strip():
            content = "\u200b"  # zero-width space — satisfies reqd, renders invisible
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
        save_chat_message(
            "user", message,
            {"attachments": json.dumps(attachments)} if attachments else None
        )
        skills_prompt = build_skills_system_prompt()

        agent_setup = frappe.get_doc("Agent Setup")
        provider = (agent_setup.provider or "openrouter").strip().lower()
        _provider_defaults = {
            "openai":      "gpt-4o-mini",
            "openai-api":  "gpt-4o-mini",
            "openrouter":  "anthropic/claude-sonnet-4",
            "anthropic":   "claude-3-5-sonnet-latest",
            "gemini":      "gemini-2.5-pro",
        }
        model = (agent_setup.model or "").strip() or _provider_defaults.get(provider, "gpt-4o-mini")

        agent = AIAgent(
            model=model,
            quiet_mode=False,
            platform="frappe",
            ephemeral_system_prompt=skills_prompt,
            enabled_toolsets=["frappe_tools","clarify","delegation", "skills", "memory", "todo", "search", "session-search"],
            stream_delta_callback=on_token,
            tool_start_callback=on_tool_start,
            tool_complete_callback=on_tool_done,
            tool_progress_callback=on_tool_status,
        )

        result = agent.run_conversation(
            user_message=agent_message,
            conversation_history=agent_context
        )
        final_response = result["final_response"]

        save_chat_message(
            "assistant", final_response,
            {"tool_calls": json.dumps(tool_call_log)} if tool_call_log else None
        )

        frappe.db.set_value("Agent Chat", chat_id, {
            "agent_context": json.dumps(result["messages"], default=str),
            "last_active": now_datetime(),
            "message_count": (chat_doc.message_count or 0) + 2,
        })
        frappe.db.commit()

        publish("agent_done", {"response": final_response, "chat_id": chat_id})

    except Exception as e:
        frappe.log_error(title="Agent Chat Error", message=frappe.get_traceback())

        for entry in tool_call_log:
            if entry.get("status") == "running":
                entry["status"] = "interrupted"

        error_text = (
            f"Sorry, something went wrong: {e}"
            if frappe.conf.get("developer_mode")
            else "Sorry, something went wrong while processing that request. Please try again."
        )

        try:
            error_extras = {"is_error": 1}
            if tool_call_log:
                error_extras["tool_calls"] = json.dumps(tool_call_log)
            save_chat_message("assistant", error_text, error_extras)
            frappe.db.commit()
        except Exception:
            frappe.log_error(title="Agent Chat Error - DB Save", message=frappe.get_traceback())

        try:
            publish("agent_error", {"response": error_text, "chat_id": chat_id})
        except Exception:
            pass