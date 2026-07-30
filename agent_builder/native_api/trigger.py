# agent_builder/native_api/trigger.py
"""Runs Agent Triggers: 'when X happens, run agent Y' (or workflow Y, if
the trigger's workflow_name is set instead of/alongside agent_name).

Deliberately thin. It builds a Conversation exactly like verify.py's chat
path does, stamps trigger provenance onto the session, renders the
trigger's input_template into the first user message, then calls the same
Agent.run() closed loop — no streaming callbacks, since nothing is watching
live. Everything downstream (checkpointing, cost tracking, tool_calls,
ended_reason) is identical to a chat session for free.

Workflow-targeted triggers skip all of that and go straight to
workflow.engine.run_workflow with the raw context as initial_input — see
fire_trigger below.
"""

import logging

import frappe
from frappe.utils.safe_exec import get_safe_globals

from agent_builder.native_api.agent.runner import SessionProvenance, run_headless_agent

logger = logging.getLogger(__name__)


# =========================================================================
# Entry points
# =========================================================================


@frappe.whitelist()
def fire_trigger(trigger_name: str, context: dict):
	"""Enqueue a headless agent (or workflow) run for the given Agent Trigger.

	context: whatever data the trigger needs to render input_template /
	evaluate condition — e.g. {"doc": doc.as_dict()} for a DocType Event.

	If workflow_name is set, this fires the workflow directly with
	`context` as its initial_input — no agent involved, no input_template
	rendering (a workflow's Trigger step is declarative-only and doesn't
	consume input_template the way an agent's first user turn does).
	agent_name is unused in that case even if also set; a trigger with
	both fields set fires the workflow, not the agent.
	"""
	trigger = frappe.get_cached_doc("Agent Trigger", trigger_name)
	if not trigger.is_enabled:
		return

	if trigger.condition and not _evaluate_condition(trigger.condition, context):
		return

	if trigger.get("workflow_name"):
		frappe.enqueue(
			method="agent_builder.native_api.workflow.engine.run_workflow",
			queue="short",
			timeout=300,
			workflow_name=trigger.workflow_name,
			initial_input=context,
		)
		return

	frappe.enqueue(
		method="agent_builder.native_api.trigger.run_triggered_agent",
		queue="short",
		timeout=300,
		trigger_name=trigger_name,
		context=context,
	)


def run_triggered_agent(trigger_name: str, context: dict):
	"""Background job body: build a stamped session and run the agent loop."""
	trigger = frappe.get_doc("Agent Trigger", trigger_name)

	rendered_message = frappe.render_template(trigger.input_template or "", context)

	provenance = SessionProvenance(
		trigger_type=trigger.trigger_type,
		trigger_source=trigger.doctype_name if trigger.trigger_type == "DocType Event" else trigger_name,
		trigger_ref=_extract_ref(context),
	)

	result = run_headless_agent(
		agent_name=trigger.agent_name,
		input_message=rendered_message,
		provenance=provenance,
		user=trigger.run_as_user or "Administrator",
	)

	# run_headless_agent already commits and saves the session
	# Emit done event for any listeners
	conversation = frappe.get_doc("Agent session", result.session_id)
	if result.ended_reason == "Completed":
		conversation.emit_done(result.response)
	else:
		conversation.emit_error(f"Agent ended with: {result.ended_reason}")


# =========================================================================
# DocType Event hook entrypoint
# =========================================================================
# Wire this once in hooks.py's doc_events for whichever doctypes/events you
# want to support, e.g.:
#
#   doc_events = {
#       "*": {
#           "after_insert": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_update": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_submit": "agent_builder.native_api.trigger.handle_doctype_event",
#       }
#   }
#
# Using "*" plus the doctype_name/doctype_event filter on Agent Trigger
# means you never have to touch hooks.py again to add a new triggered
# agent — just create a new Agent Trigger record.


def handle_doctype_event(doc, event):
	matches = frappe.get_all(
		"Agent Trigger",
		filters={
			"trigger_type": "DocType Event",
			"doctype_name": doc.doctype,
			"doctype_event": event,
			"is_enabled": 1,
		},
		pluck="name",
	)
	for trigger_name in matches:
		fire_trigger(trigger_name, {"doc": doc.as_dict()})


# =========================================================================
# Scheduled hook entrypoint
# =========================================================================
# Wire in hooks.py's scheduler_events (cron_expression is stored on the
# Agent Trigger record for reference/UI display; Frappe's own scheduler
# config still needs the matching cron entry pointing at this function,
# passing the trigger_name — e.g. via a small per-trigger wrapper, or by
# scanning all "Scheduled" triggers from one hourly job and checking each
# one's cron_expression yourself if you want fully dynamic scheduling).


def run_scheduled_trigger(trigger_name: str):
	fire_trigger(trigger_name, {})


# =========================================================================
# Helpers
# =========================================================================


def _extract_ref(context: dict):
	doc_ctx = context.get("doc") if isinstance(context, dict) else None
	if isinstance(doc_ctx, dict):
		return doc_ctx.get("name")
	return None


def _evaluate_condition(condition: str, context: dict) -> bool:
	"""Evaluate a trigger's guard expression against its context using
	Frappe's sandboxed eval (same mechanism as Server Script conditions) —
	never raw eval() on user-editable text.
	"""
	try:
		safe_globals = get_safe_globals()
		safe_globals.update(context)
		return bool(frappe.safe_eval(condition, safe_globals))
	except Exception:
		logger.warning("Agent Trigger condition failed to evaluate: %s", condition)
		return False