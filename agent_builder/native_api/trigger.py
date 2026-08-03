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

import ast
import logging
import re
from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime
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
        if trigger.input_template:
            initial_input = _render_template_to_object(trigger.input_template, context)
        else:
            initial_input = context

        frappe.enqueue(
            method="agent_builder.native_api.workflow.engine.run_workflow",
            queue="short",
            timeout=300,
            workflow_name=trigger.workflow_name,
            initial_input=initial_input,
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

    if trigger.input_template:
        rendered_message = _render_template_to_string(trigger.input_template, context)
    else:
        # Same "blank = pass the whole context through" convention as
        # workflow-targeted triggers (see fire_trigger) — an agent's
        # first turn has to be a text message rather than a raw dict, so
        # this serializes the context (including the full 'doc') as
        # readable JSON instead of leaving the agent with an empty message.
        rendered_message = frappe.as_json(context, indent=2)

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
# Webhook entrypoint
# =========================================================================
# No hooks.py wiring needed — this is just a normal whitelisted endpoint,
# reachable at:
#   POST /api/method/agent_builder.native_api.trigger.receive_webhook
#   {"trigger_name": "...", "token": "<webhook_token from the trigger>", ...payload}
# allow_guest=True because an external system calling this has no Frappe
# session — the token IS the auth. Never remove the token check below.


@frappe.whitelist(allow_guest=True)
def receive_webhook(trigger_name: str, token: str, **payload):
    if not frappe.db.exists("Agent Trigger", trigger_name):
        frappe.throw("Unknown trigger", frappe.DoesNotExistError)

    trigger = frappe.get_cached_doc("Agent Trigger", trigger_name)
    if trigger.trigger_type != "Webhook":
        frappe.throw("This trigger is not a Webhook-type trigger")
    if not trigger.webhook_token or token != trigger.webhook_token:
        frappe.throw("Invalid token", frappe.PermissionError)

    # Frappe injects 'cmd' into every whitelisted call's kwargs — strip it
    # so it doesn't leak into the workflow/agent's context as real payload.
    payload.pop("cmd", None)
    fire_trigger(trigger_name, payload)
    return {"status": "accepted"}


# =========================================================================
# DocType Event hook entrypoint
# =========================================================================
# REQUIRES a one-time manual edit to your app's hooks.py — this is the
# most likely reason a DocType Event trigger does nothing with no error:
# handle_doctype_event below is never called by Frappe unless you wire it
# in doc_events yourself. There is no way to register this automatically
# from inside this file. Add once:
#
#   doc_events = {
#       "*": {
#           "after_insert": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_update": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_submit": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_cancel": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_trash": "agent_builder.native_api.trigger.handle_doctype_event",
#       }
#   }
#
# Using "*" plus the doctype_name/doctype_event filter on Agent Trigger
# means you never have to touch hooks.py again to add a new triggered
# workflow/agent — just create a new Agent Trigger record. After editing
# hooks.py, run `bench build` / restart bench for it to take effect.


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
# Also REQUIRES a one-time hooks.py edit, but only ONE — unlike a naive
# per-trigger cron entry, run_due_scheduled_triggers below checks every
# enabled Scheduled-type Agent Trigger's own cron_expression itself, so
# creating a new Scheduled trigger never needs another hooks.py edit.
# Wire once, at Frappe's own per-minute cadence:
#
#   scheduler_events = {
#       "cron": {
#           "* * * * *": ["agent_builder.native_api.trigger.run_due_scheduled_triggers"]
#       }
#   }
#
# Requires the 'croniter' package (already a transitive Frappe dependency
# — it's what Frappe's own scheduler uses internally).


def run_due_scheduled_triggers():
    try:
        import croniter
    except ImportError:
        logger.error("croniter is not installed — Scheduled Agent Triggers cannot fire.")
        return

    triggers = frappe.get_all(
        "Agent Trigger",
        filters={"trigger_type": "Scheduled", "is_enabled": 1},
        fields=["name", "cron_expression", "last_triggered_at"],
    )
    now = now_datetime()

    for t in triggers:
        if not t.cron_expression:
            continue

        # First-ever check has no last_triggered_at to anchor from — use
        # "1 minute ago" so a cron due right now fires immediately instead
        # of waiting a full cycle.
        base = get_datetime(t.last_triggered_at) if t.last_triggered_at else now - timedelta(minutes=1)

        try:
            # FIX: get_next() expects a type (defaults to datetime.datetime). 
            # Passing get_datetime throws a TypeError which gets silently caught.
            next_due = croniter.croniter(t.cron_expression, base).get_next()
        except Exception:
            logger.warning("Agent Trigger %s has an invalid cron_expression: %s", t.name, t.cron_expression)
            continue

        if next_due <= now:
            # Stamped before firing, not after — a slow/stuck run
            # shouldn't cause this same minute to double-fire on the next
            # scheduler tick.
            frappe.db.set_value("Agent Trigger", t.name, "last_triggered_at", now, update_modified=False)
            frappe.db.commit()
            fire_trigger(t.name, {})


# =========================================================================
# Template rendering helpers
# =========================================================================
# These two functions are the single source of truth for how trigger
# input_template strings become runtime values. They support BOTH:
#
#   {{ doc.field }}   — embedded field reference (Jinja renders the value
#                       inline, the surrounding template is parsed as JSON)
#   {{ doc }}         — whole-variable passthrough (returns the native
#                       Python object directly, NOT its str() repr)
#
# The whole-variable case is the one that was broken before: Jinja's
# default stringification of a dict produces a single-quoted Python repr
# like {'name': 'CUST-001'}, which fails JSON parsing and fell through
# to the {"rendered": "..."} fallback — silently losing the data.
#
# The same two patterns apply to workflow step args / input_mapping /
# delegate task text in engine.py — if engine.py doesn't already have
# equivalent logic, it should import and reuse these helpers so the
# behaviour is identical across triggers and steps.


def _render_template_to_object(template: str, context: dict):
    """Render a Jinja template and return a Python object (dict, list, str,
    etc.). Used by workflow-targeted triggers where initial_input needs to
    be a structured value, not a string.

    Patterns supported:
      {{ doc.field }}  — embedded in a larger JSON template:
                         '{"customer": "{{ doc.customer }}"}'
                         → Jinja renders the field value inline, the whole
                         string is parsed as JSON → dict
      {{ doc }}        — standalone whole-variable passthrough:
                         → returns the native Python object (dict/list)
                         directly, bypassing Jinja's str() repr entirely
      {{ output }}     — same, for workflow step contexts where the
                         previous step's output is the variable

    Fallback chain for mixed/complex templates:
      1. Jinja render → JSON parse
      2. Jinja render → Python literal_eval (handles single-quoted dict
         reprs from {{ var }} embedded in non-JSON templates)
      3. Wrap as {"rendered": "..."} (last resort, preserves the text)
    """
    stripped = template.strip()

    # Standalone {{ var }} or {{ var.path.sub }} — return native object
    # directly, no stringification step at all.
    m = re.match(r"^\{\{\s*([\w.]+)\s*\}\}$", stripped)
    if m:
        value = _resolve_dotted(context, m.group(1))
        if value is not None:
            return value

    # Standard Jinja render for everything else (embedded refs, mixed
    # templates, literal JSON with {{ }} placeholders, etc.)
    rendered = frappe.render_template(template, context)

    # Try JSON parse first — handles templates like
    #   {"customer": "{{ doc.customer }}"}
    # where Jinja fills in the field value and the whole string is JSON.
    try:
        return frappe.parse_json(rendered)
    except Exception:
        pass

    # Try Python literal eval — handles cases where Jinja's str() of a
    # dict/list produced a single-quoted repr inside a larger template.
    # ast.literal_eval safely parses Python literals (dict, list, str,
    # int, float, bool, None) without executing code.
    try:
        return ast.literal_eval(rendered)
    except Exception:
        pass

    # Last resort: wrap the rendered string so it's at least visible
    # to the downstream consumer rather than crashing the run.
    return {"rendered": rendered}


def _render_template_to_string(template: str, context: dict) -> str:
    """Render a Jinja template to a string, outputting whole-variable
    references as readable JSON rather than Python dict repr.

    Used by agent-targeted triggers where the rendered template becomes
    the agent's first user message (which must be a string, not an object).

    For standalone {{ doc }} where doc is a dict/list, outputs
    frappe.as_json(doc) so the agent receives:
      {"name": "CUST-001", "customer_name": "John Doe", ...}
    instead of Jinja's default:
      {'name': 'CUST-001', 'customer_name': 'John Doe', ...}
    (single quotes, not valid JSON, harder to read).

    For embedded {{ doc.field }} inside a larger template, standard
    Jinja rendering applies — the field's value is stringified inline
    by Jinja as usual.
    """
    stripped = template.strip()

    # Standalone {{ var }} or {{ var.path.sub }} — output as JSON string
    m = re.match(r"^\{\{\s*([\w.]+)\s*\}\}$", stripped)
    if m:
        value = _resolve_dotted(context, m.group(1))
        if value is not None:
            if isinstance(value, str):
                return value
            return frappe.as_json(value, indent=2)

    # Standard Jinja render for embedded field refs and mixed templates
    return frappe.render_template(template, context)


def _resolve_dotted(context: dict, path: str):
    """Resolve a dotted path like 'doc.customer.name' against a context
    dict. Walks dicts by key and objects by attribute.

    Returns None if any segment is missing — the caller decides whether
    None is acceptable (template_to_object returns it as-is; the regex
    guard in both helpers means a None result falls through to the
    standard Jinja render path).
    """
    value = context
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif value is not None:
            value = getattr(value, part, None)
        else:
            return None
    return value


# =========================================================================
# Other helpers
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