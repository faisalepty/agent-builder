# agent_builder/native_api/verify.py
import frappe
import asyncio

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.agent.agent import Agent, MaxTurnsError



@frappe.whitelist()
def get_messages(chat_id, limit=50, start=0):
    """Load display messages for a chat — paginated."""
    
    if not frappe.db.exists("Agent session", chat_id):
        frappe.throw("Chat not found", frappe.DoesNotExistError)
        
    user = frappe.db.get_value("Agent session", chat_id, "user")
    if user != frappe.session.user:
        frappe.throw("Not authorised", frappe.PermissionError)

    title = frappe.db.get_value("Agent session", chat_id, "title")

    messages = frappe.get_list(
        "Agent Message",
        filters={"parent": chat_id, "parenttype": "Agent session"},
        fields=["name", "role", "content", "timestamp", "attachments", "tool_calls", "is_error"],
        order_by="timestamp asc",
        limit_page_length=limit,
        start=start,
        ignore_permissions=True
    )
        
    return {"messages": messages, "title": title}


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

