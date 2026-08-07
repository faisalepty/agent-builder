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
    # Wired to doc_events["*"], so this fires on every doctype's insert —
    # including internal doctype-sync inserts that bench migrate itself
    # performs while importing other doctypes' JSON definitions. At that
    # point in the migrate sequence Agent Trigger's own table may not
    # exist yet, so skip entirely during migrate/install rather than
    # querying a table that might not be there.
    if frappe.flags.in_migrate or frappe.flags.in_install:
        return
    if not frappe.db.table_exists("Agent Trigger"):
        return

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
# Scheduled Job Type sync
# =========================================================================
# No hooks.py wiring needed at all — this is the same mechanism Server
# Script uses for its "Scheduler Event" script_type: each Scheduled Agent
# Trigger owns a real `Scheduled Job Type` record, and Frappe's own
# scheduler daemon (frappe/utils/scheduler.py: enqueue_events(), on its
# normal tick — default every 4 min, configurable via
# scheduler_tick_interval) picks it up, checks it against croniter and
# last_execution itself, and enqueues it when due.
#
# Called from BOTH places an Agent Trigger gets written from:
#   - agent_builder.py: _sync_trigger_steps  (canvas trigger node)
#   - agent_builder.py: create_trigger / toggle_trigger  (standalone tab)
# so a Scheduled trigger behaves identically no matter which UI made it.
# Agent Trigger has no custom controller, so this isn't a doctype hook —
# it's just called explicitly at every one of those write sites.


def sync_scheduled_job_type(trigger_doc):
    job_name = f"agent_trigger::{trigger_doc.name}"
    exists = frappe.db.exists("Scheduled Job Type", job_name)

    if trigger_doc.trigger_type != "Scheduled" or not trigger_doc.is_enabled:
        if exists:
            frappe.db.delete("Scheduled Job Type", job_name)
        return

    event_frequency = trigger_doc.get("event_frequency") or "Daily"
    is_cron = event_frequency == "Cron"
    # "X Long" just routes to the long-running worker queue in Server
    # Script — the underlying Scheduled Job Type frequency is still the
    # base value ("Daily", "Weekly", etc). NOTE: verify the actual field
    # Scheduled Job Type uses for queue selection on your Frappe version
    # (bench console: frappe.get_meta("Scheduled Job Type").fields) before
    # relying on the `job.queue = "long"` line below — I'm not fully
    # certain that's the right field name/API for your version.
    is_long = event_frequency.endswith(" Long")
    base_frequency = event_frequency.replace(" Long", "") if is_long else event_frequency

    if is_cron and not trigger_doc.cron_expression:
        if exists:
            frappe.db.delete("Scheduled Job Type", job_name)
        return

    if exists:
        job = frappe.get_doc("Scheduled Job Type", job_name)
    else:
        job = frappe.new_doc("Scheduled Job Type")
        job.set("__newname", job_name)  # key the job by our own name, not autoname

    job.method = "agent_builder.native_api.trigger.run_scheduled_trigger_job"
    job.arguments = frappe.as_json({"trigger_name": trigger_doc.name})
    job.stopped = 0

    if is_cron:
        job.frequency = "Cron"
        job.cron_format = trigger_doc.cron_expression
    else:
        job.frequency = base_frequency
        job.cron_format = None
        if is_long and hasattr(job, "queue"):
            job.queue = "long"

    job.save(ignore_permissions=True)


def run_scheduled_trigger_job(trigger_name: str, **kwargs):
    """The `method` every synced Scheduled Job Type points to. Frappe
    passes the job's `arguments` JSON through as kwargs."""
    if not frappe.db.get_value("Agent Trigger", trigger_name, "is_enabled"):
        return
    frappe.db.set_value("Agent Trigger", trigger_name, "last_triggered_at", now_datetime(), update_modified=False)
    frappe.db.commit()
    fire_trigger(trigger_name, {})


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
        frappe.log_error(f"Agent Trigger condition failed to evaluate: {condition}")
        return False