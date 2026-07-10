# agent_builder/native_api/agent/telemetry_api.py
"""
Thin whitelisted endpoints for the Hermes frontend and eval scripts to write
telemetry fields that don't originate from inside Agent.run() — user
feedback (a UI click after the fact) and outcome/eval labels (assigned by a
reviewer or judge pass, asynchronously).

Deliberately NOT part of conversation.py's hot path — these are called from
chat_ui.js on a thumbs-up/down click, or from an eval batch script, never
from the agent loop itself.
"""
import frappe

from agent_builder.native_api.agent.conversation import Conversation, SESSION_DOCTYPE


@frappe.whitelist()
def submit_feedback(session_id: str, feedback: str, note: str = None):
    """Called by chat_ui.js when a user taps thumbs up/down on a reply.

    feedback must be '👍', '👎', or 'none' (to clear/reset).
    """
    if frappe.session.user == "Guest":
        frappe.throw("Login required", frappe.PermissionError)

    # Ownership check — a user should only be able to rate their own sessions.
    owner = frappe.db.get_value(SESSION_DOCTYPE, session_id, "user")
    if owner is None:
        frappe.throw(f"No such session: {session_id}")
    if owner != frappe.session.user and "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted to rate this session", frappe.PermissionError)

    Conversation.set_user_feedback_by_session_id(session_id, feedback, note)
    return {"ok": True}


@frappe.whitelist()
def set_session_outcome(session_id: str, outcome: str):
    """Called from an eval review UI or LLM-judge batch script — requires
    elevated permissions since this is a quality judgment, not raw telemetry.
    """
    if "System Manager" not in frappe.get_roles() and "Agent Eval Reviewer" not in frappe.get_roles():
        frappe.throw("Not permitted to set session outcomes", frappe.PermissionError)

    conversation = Conversation(session_id=session_id)
    conversation.set_outcome(outcome)
    return {"ok": True}