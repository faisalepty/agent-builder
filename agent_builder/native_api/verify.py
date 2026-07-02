# agent_builder/native_api/verify.py
import re

import frappe
import asyncio

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.agent.agent import Agent, MaxTurnsError


@frappe.whitelist()
def get_messages(chat_id, limit=50, start=0):
    """Load display messages for a chat — paginated.

    Reshapes the two normalized child tables (Agent Message, Agent Tool
    Call) back into the turn-based shape the widget's history renderer
    expects — the same shape the *live* renderer builds turn-by-turn
    while streaming:

        { role: "assistant", content, is_error,
          tool_calls: [{tool, args, status, elapsed_ms, result|error}],
          reasoning: {text, elapsed_ms} | null }

    "reasoning" and legacy "tool" rows are never sent back as their own
    message entries — the frontend only renders user/assistant rows;
    everything else is folded into the assistant row it belongs to.
    """
    TOOL_CALL_DOCTYPE = "Agent Tool Call"
    if not frappe.db.exists("Agent session", chat_id):
        frappe.throw("Chat not found", frappe.DoesNotExistError)

    user = frappe.db.get_value("Agent session", chat_id, "user")
    if user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    title = frappe.db.get_value("Agent session", chat_id, "title")

    limit = int(limit)
    start = int(start)

    rows = frappe.get_list(
        "Agent Message",
        filters={"parent": chat_id, "parenttype": "Agent session"},
        fields=["name", "message_id", "role", "content", "timestamp",
                "attachments", "is_error"],
        order_by="timestamp asc, idx asc",
        limit_page_length=limit,
        start=start,
        ignore_permissions=True,
    )

    message_ids = [r.message_id for r in rows if r.message_id]

    # Group tool calls by the assistant message that requested them.
    tool_calls_by_parent = {}
    if message_ids:
        tc_rows = frappe.get_list(
            TOOL_CALL_DOCTYPE,
            filters={
                "parent": chat_id,
                "parenttype": "Agent session",
                "parent_message": ["in", message_ids],
            },
            fields=["parent_message", "call_id", "tool_name", "arguments",
                    "status", "result", "error", "elapsed_ms"],
            order_by="idx asc",
            ignore_permissions=True,
        )
        for tc in tc_rows:
            tool_calls_by_parent.setdefault(tc.parent_message, []).append({
                "tool": tc.tool_name,
                "args": _safe_json(tc.arguments),
                "status": tc.status,            # "pending" | "running" | "success" | "error"
                "elapsed_ms": tc.elapsed_ms,
                "result": tc.result,
                "error": tc.error,
            })

    # Walk rows in write order and pair each reasoning row with the very
    # next assistant row — that's the order Conversation writes them in
    # (_flush_reasoning() runs right before add_assistant_message()'s
    # append, and again before each emit_tool_start()).
    #
    # Caveat: if a reasoning row lands as the very last row of a page and
    # its assistant row falls on the next page, this pairing breaks across
    # the page boundary. Only matters once conversations exceed `limit`
    # messages — fine for now, flag if you start paginating mid-turn.
    messages = []
    pending_reasoning = None

    for row in rows:
        if row.role == "reasoning":
            pending_reasoning = {"text": row.content, "elapsed_ms": None}
            continue

        if row.role == "assistant":
            messages.append({
                "role": "assistant",
                "content": row.content,
                "is_error": row.is_error,
                "tool_calls": tool_calls_by_parent.get(row.message_id, []),
                "reasoning": pending_reasoning,
            })
            pending_reasoning = None

        elif row.role == "user":
            messages.append({
                "role": "user",
                "content": row.content,
                "attachments": row.attachments,
            })

        # Any other role (e.g. a legacy "tool" row from before the
        # migration) is intentionally skipped — the new schema never
        # produces a standalone tool-result message; results live on the
        # tool call row itself and are attached to their parent assistant
        # message above.

    return {"messages": messages, "title": title}


def _safe_json(value):
    if not value:
        return None
    try:
        return frappe.parse_json(value)
    except Exception:
        return value
    
    
def _slugify(value):
    """Turn a skill's display name into a clean /slash-command token."""
    if not value:
        return ""
   
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")

    

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
    


@frappe.whitelist()
def get_chats():
    """Return the current user's chat list."""
    chats = frappe.get_list(
        "Agent session",
        filters={"user": frappe.session.user, "status": "Active"},
        fields=["name", "title", "last_active", "message_count"],
        order_by="last_active desc",
        limit_page_length=50,
    )
    return {"chats": chats}


@frappe.whitelist()
def chat(message, chat_id=None, attachments=None):
    """API Endpoint: Queues the message for background processing."""
    user = frappe.session.user
    attachments = frappe.parse_json(attachments) if attachments else []

    if not chat_id:
        chat_id = Conversation(user=user).session_id

    frappe.enqueue(
        method="agent_builder.native_api.verify.process_agent_chat",
        queue="short",
        timeout=300,
        now=frappe.flags.in_test,
        message=message,
        chat_id=chat_id,
        attachments=attachments,
        user=user
    )

    return {"status": "queued", "chat_id": chat_id}


def process_agent_chat(message, chat_id, attachments, user):
    """Background Job: Executes the agent loop."""
    agent_message = message
    if attachments:
        file_lines = "\n".join(
            f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}"
            for a in attachments
        )
        agent_message = f"{message}\n\n[Attached files]\n{file_lines}".strip()

    conversation = Conversation(session_id=chat_id, user=user)

    try:
        # Instantiate the standalone agent and run it
        agent = Agent()
        conversation.add_user_message(agent_message)

        final_response = asyncio.run(
            agent.run(
                conversation, 
                on_token=conversation.emit_token, 
                on_reasoning=conversation.emit_reasoning
            )
        )

        frappe.db.commit()
        conversation.emit_done(final_response)

    except MaxTurnsError as e:
        frappe.db.commit()
        conversation.emit_error("Agent took too long.")
        frappe.log_error("Agent Max Turns", str(e))

    except Exception as e:
        frappe.db.commit()
        error_text = str(e) if frappe.conf.get("developer_mode") else "Sorry, something went wrong."
        conversation.emit_error(error_text)
        frappe.log_error("Agent Chat Error", frappe.get_traceback())

