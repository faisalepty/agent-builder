# verify.py
import frappe
import asyncio
from pathlib import Path

from agent_builder.native_api.agent.conversation import Conversation
from agent_builder.native_api.agent.agent import Agent, MaxTurnsError
from agent_builder.native_api.providers.openai_api import OpenAIProvider
from agent_builder.native_api.tools.decorator import ToolRegistry
from agent_builder.native_api.tools.loader import load_tools
from agent_builder.native_api.tools.internal.skill_list import skill_list

# FIX: resolve the tools directory relative to this file, not the worker's
# cwd. "./tools" resolved against an RQ worker's cwd (usually the bench
# root) was very likely loading zero tools silently.
TOOLS_DIR = Path(__file__).resolve().parent / "tools"


@frappe.whitelist()
def chat(message, chat_id=None, attachments=None):
    user = frappe.session.user

    # FIX: Frappe v17 removed the second argument from parse_json
    attachments = frappe.parse_json(attachments) if attachments else []

    if not chat_id:
        # Conversation.__init__ already inserts the new doc when no
        # session_id is passed — no need to create it twice.
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
    """Background job."""
    agent_message = message
    if attachments:
        file_lines = "\n".join(
            f"- {a.get('file_name', 'file')}: {a.get('file_url', '')}"
            for a in attachments
        )
        agent_message = f"{message}\n\n[Attached files]\n{file_lines}".strip()

    # Conversation is created up front (outside the try) so that even if
    # something below blows up, we still have a valid `conversation` to
    # publish the error event through with the correct room.
    conversation = Conversation(session_id=chat_id, user=user)

    try:
        registry = ToolRegistry()
        load_tools(registry, str(TOOLS_DIR))

        # Sanity check — if this ever logs 0, tool loading silently failed
        # and the agent is running with no tools available.
        frappe.logger().info(f"[agent_chat] loaded {len(registry.get_tool_schemas())} tool schemas from {TOOLS_DIR}")

        skills_context = skill_list()

        system_prompt = (
            "You are an advanced automated operational runtime framework.\n\n"
            "### AVAILABLE SKILLS\n"
            f"{skills_context}\n\n"
            "Use `skill_view` to read a skill's full specification before acting on it."
        )

        provider = OpenAIProvider(model="openrouter/owl-alpha")
        agent = Agent(
            provider=provider,
            registry=registry,
            system_prompt=system_prompt,
            max_turns=20,
        )

        conversation.add_user_message(agent_message)

        final_response = asyncio.run(agent.run(conversation, on_token=conversation.emit_token))

        # FIX: explicit commit — background workers don't auto-commit the
        # way a request context does. Without this, the saved messages and
        # the agent_done event can race a process exit / be invisible to
        # the next request.
        frappe.db.commit()

        # FIX: route through Conversation so the room is computed exactly
        # the same way (get_user_room) as every other event in this turn,
        # rather than re-deriving f"user_{user}" here.
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