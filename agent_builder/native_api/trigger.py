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


from agent_builder.native_api.tools.clarify_approval_tools.notify import (
    add_agent_comment,
    dedupe_users,
    excerpt_text,
    notify_run_complete,
    notify_run_started,
    system_managers,
)
from agent_builder.native_api.agent.runner import SessionProvenance, run_headless_agent
from agent_builder.native_api.providers.attachments import _resolve_attachments

logger = logging.getLogger(__name__)


# =========================================================================
# Entry points
# =========================================================================


@frappe.whitelist()
def fire_trigger(trigger_name: str, context: dict):
    """Enqueue a headless agent (or workflow) run for the given Agent Trigger.

    context: whatever data the trigger needs to render input_template /
    evaluate condition — e.g. {"doc": doc.as_dict()} for a DocType Event.
    handle_doctype_event additionally injects "acting_user" (the session
    user at fire time — the worker has no request session to read it
    from later) and "event" (the doc event name). Both keys are harmless
    extras for templates/conditions and are consumed by the notification
    helpers.

    If workflow_name is set, this fires the workflow directly with
    `context` (plus any resolved attachments merged in) as its
    initial_input — no agent involved, no input_template rendering (a
    workflow's Trigger step is declarative-only and doesn't consume
    input_template the way an agent's first user turn does).
    agent_name is unused in that case even if also set; a trigger with
    both fields set fires the workflow, not the agent.
    """
    trigger = frappe.get_cached_doc("Agent Trigger", trigger_name)
    if not trigger.is_enabled:
        return

    if trigger.condition and not _evaluate_condition(trigger.condition, context):
        return

    doctype, docname = _doc_info(context)

    # ── Start signal ─────────────────────────────────────────────────
    # Sent in the SAME request as the user's save (DocType Event path),
    # so the causal link — "I submitted this → an agent is now working
    # on it" — is instant. Only fires for human-caused runs: scheduled,
    # webhook, and console callers pass no acting_user, and system users
    # (Administrator/Guest) are dropped by dedupe inside the helper.
    # Covers BOTH branches below (workflow and agent).
    acting_user = context.get("acting_user") if isinstance(context, dict) else None
    if acting_user:
        label = f"'{trigger.trigger_name}' queued"
        if docname:
            label += f" for {docname}"
        notify_run_started([acting_user], label, doctype=doctype, docname=docname)

    if trigger.get("workflow_name"):
        if trigger.input_template:
            initial_input = _render_template_to_object(trigger.input_template, context)
        else:
            initial_input = context

        attachments = _resolve_attachments(trigger, context)
        if attachments:
            if isinstance(initial_input, dict):
                initial_input.setdefault("attachments", attachments)
            else:
                initial_input = {"value": initial_input, "attachments": attachments}

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
    """Background Job: run the trigger's agent end-to-end, then notify.

    Notification model (see notify.py for channel rationale):
      - START toast was already sent in fire_trigger, inside the user's
        own request — nothing to do here at run start. (The old
        worker-side "is running…" ping is removed: it arrived seconds
        after the fire-time toast, adding noise, not information.)
      - OUTCOME is persistent: a Notification Log row (bell) per
        recipient linking to this run's Agent session, plus a timeline
        Comment on the triggering document for anyone who opens it later.
    """
    trigger = frappe.get_doc("Agent Trigger", trigger_name)

    if trigger.input_template:
        rendered_message = _render_template_to_string(trigger.input_template, context)
    else:
        rendered_message = frappe.as_json(context, indent=2)

    provenance = SessionProvenance(
        trigger_type=trigger.trigger_type,
        trigger_source=trigger.doctype_name if trigger.trigger_type == "DocType Event" else trigger_name,
        trigger_ref=_extract_ref(context),
    )

    skill_injection = None
    if trigger.agent_name:
        skill = frappe.get_doc("Skill", trigger.agent_name)
        if not skill.is_agent:
            frappe.log_error(f"Agent Trigger '{trigger_name}' -> Skill '{skill.name}' is not marked is_agent")
            return
        if not skill.is_enabled:
            frappe.log_error(f"Agent Trigger '{trigger_name}' -> Skill '{skill.name}' is disabled")
            return
        skill_injection = skill.content

    result = run_headless_agent(
        agent_name=None,
        input_message=rendered_message,
        provenance=provenance,
        user=trigger.run_as_user or "Administrator",
        skill_injection=skill_injection,
        attachments=_resolve_attachments(trigger, context),
    )

    _notify_run_outcome(trigger, context, result)
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
#           "before_insert": "agent_builder.native_api.trigger.handle_doctype_event",
#           "after_insert": "agent_builder.native_api.trigger.handle_doctype_event",
#           "before_save": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_update": "agent_builder.native_api.trigger.handle_doctype_event",
#           "before_submit": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_submit": "agent_builder.native_api.trigger.handle_doctype_event",
#           "before_cancel": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_cancel": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_update_after_submit": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_trash": "agent_builder.native_api.trigger.handle_doctype_event",
#           "after_delete": "agent_builder.native_api.trigger.handle_doctype_event",
#           "on_change": "agent_builder.native_api.trigger.handle_doctype_event",
#       }
#   }
#
# This list must stay in sync with the Agent Trigger doctype's
# doctype_event Select options (agent_trigger.json) — an event picked in
# the UI that isn't also a key here will save fine and just never fire,
# with no error anywhere. Deliberately NOT wired: "validate" (fires
# pre-commit inside the save transaction — enqueuing an agent there can
# fire even if the save later rolls back) and "before_naming"/"autoname"
# (doc.name doesn't exist yet).
#
# Using "*" plus the doctype_name/doctype_event filter on Agent Trigger
# means you never have to touch hooks.py again to add a new triggered
# workflow/agent — just create a new Agent Trigger record. After editing
# hooks.py, run `bench build` / restart bench for it to take effect.


# Frappe's own noisy internal doctypes fire constantly and will never
# have a matching Agent Trigger — bail before even touching the cache.
_DOCTYPE_EVENT_DENYLIST = {
    "Version",
    "Activity Log",
    "Error Log",
    "RQ Job",
    "RQ Job Update",
    "Route History",
    "Access Log",
    "View Log",
    "Notification Log",
    "Email Queue",
    "Comment",
}

_TRIGGER_MAP_CACHE_KEY = "agent_builder:doctype_event_trigger_map"


def _get_doctype_event_trigger_map() -> dict:
    """Redis-cached {(doctype, event): [trigger_name, ...]} for every
    enabled DocType Event trigger. Rebuilt from a single DB query when the
    cache is cold or was invalidated; a plain redis GET the rest of the
    time — no DB round trip on the hot path (every doc write in the
    system runs through handle_doctype_event below).
    """
    cache = frappe.cache()
    cached = cache.get_value(_TRIGGER_MAP_CACHE_KEY)
    if cached is not None:
        return cached

    rows = frappe.get_all(
        "Agent Trigger",
        filters={"trigger_type": "DocType Event", "is_enabled": 1},
        fields=["name", "doctype_name", "doctype_event"],
    )
    mapping: dict = {}
    for r in rows:
        mapping.setdefault((r.doctype_name, r.doctype_event), []).append(r.name)

    # No expiry — invalidated explicitly by invalidate_trigger_cache()
    # below whenever an Agent Trigger is written. Worst case on a missed
    # invalidation path is a stale map until the next explicit clear or
    # process restart, not a crash.
    cache.set_value(_TRIGGER_MAP_CACHE_KEY, mapping)
    return mapping


def invalidate_trigger_cache():
    """Call this from every write path that creates/edits/deletes/toggles
    an Agent Trigger (agent_builder.py: create_trigger, toggle_trigger,
    _sync_trigger_steps — the same call sites that already call
    sync_scheduled_job_type — plus an Agent Trigger doctype hook if it can
    also be edited straight from Desk). Cheap: just drops the cache key,
    next handle_doctype_event call rebuilds it from one query."""
    frappe.cache().delete_value(_TRIGGER_MAP_CACHE_KEY)


def handle_doctype_event(doc, event):
    # Wired to doc_events["*"], so this fires on every doctype's insert —
    # including internal doctype-sync inserts that bench migrate itself
    # performs while importing other doctypes' JSON definitions. At that
    # point in the migrate sequence Agent Trigger's own table may not
    # exist yet, so skip entirely during migrate/install rather than
    # querying a table that might not be there.
    if frappe.flags.in_migrate or frappe.flags.in_install:
        return
    if doc.doctype in _DOCTYPE_EVENT_DENYLIST:
        return
    if not frappe.db.table_exists("Agent Trigger"):
        return

    # Cheap in-memory dict lookup, not a query, on the hot path.
    matches = _get_doctype_event_trigger_map().get((doc.doctype, event))
    if not matches:
        return

    for trigger_name in matches:
        fire_trigger(trigger_name, {"doc": doc.as_dict()})

def handle_doctype_event(doc, event):
    # Wired to doc_events["*"], so this fires on every doctype's insert —
    # including internal doctype-sync inserts that bench migrate itself
    # performs while importing other doctypes' JSON definitions. At that
    # point in the migrate sequence Agent Trigger's own table may not
    # exist yet, so skip entirely during migrate/install rather than
    # querying a table that might not be there.
    if frappe.flags.in_migrate or frappe.flags.in_install:
        return
    if doc.doctype in _DOCTYPE_EVENT_DENYLIST:
        return
    if not frappe.db.table_exists("Agent Trigger"):
        return

    # Cheap in-memory dict lookup, not a query, on the hot path.
    matches = _get_doctype_event_trigger_map().get((doc.doctype, event))
    if not matches:
        return

    for trigger_name in matches:
        fire_trigger(
            trigger_name,
            {
                "doc": doc.as_dict(),
                "acting_user": frappe.session.user,
                "event": event,
            },
        )


# =========================================================================
# Scheduled trigger polling
# =========================================================================
# REQUIRES a one-time manual addition to hooks.py:
#
#   scheduler_events = {
#       "cron": {
#           "*/5 * * * *": ["agent_builder.native_api.trigger.run_due_scheduled_triggers"]
#       }
#   }
#
# then `bench migrate` (scheduler_events changes need a migrate, not just
# a restart, to register with the Scheduled Job Type table) — adjust the
# "*/5" polling interval to whatever the finest granularity any of your
# Scheduled triggers need (e.g. "* * * * *" for 1-minute cron triggers;
# every 5 min is plenty for Hourly/Daily/etc-frequency triggers).
#
# Why ONE polling job instead of one Scheduled Job Type per trigger (the
# previous design): core Frappe's Scheduled Job Type.execute() always
# calls frappe.get_attr(self.method)() with ZERO arguments — there is no
# supported way to pass a per-record argument (like which Agent Trigger
# this row belongs to) through to the callback. This is a known, still-
# open gap in core (frappe/frappe#15700, "Scheduled Job Type should
# support Arguments", filed 2022). A previous version of this file wrote
# trigger_name into an `arguments` field expecting it to come back as a
# kwarg — it never does; core silently ignores that field. Every fire
# failed with "run_scheduled_trigger_job() missing 1 required positional
# argument: 'trigger_name'" because of this.
#
# So instead of trying to get core to track N independent schedules, this
# single job (itself a completely static, argument-free Scheduled Job
# Type — the one pattern core DOES support) polls every enabled Scheduled
# Agent Trigger on each tick and decides due-ness itself, using
# last_triggered_at the same way it always did. If you still have old
# `agent_trigger::*` Scheduled Job Type records from the previous design,
# delete them — they're dead weight now, nothing creates or reads them.


def run_due_scheduled_triggers():
    """The scheduler_events entrypoint. No arguments — see module note
    above for why. Iterates every enabled Scheduled trigger and fires the
    ones that are due, updating last_triggered_at as it goes."""
    triggers = frappe.get_all(
        "Agent Trigger",
        filters={"trigger_type": "Scheduled", "is_enabled": 1},
        fields=["name", "event_frequency", "cron_expression", "last_triggered_at"],
    )
    if not triggers:
        return

    now = now_datetime()
    for t in triggers:
        try:
            if not _is_scheduled_trigger_due(t, now):
                continue
        except Exception:
            frappe.log_error(f"Agent Trigger '{t.name}': failed to evaluate due-ness")
            continue

        frappe.db.set_value("Agent Trigger", t.name, "last_triggered_at", now, update_modified=False)
        frappe.db.commit()
        fire_trigger(t.name, {})


_FREQUENCY_INTERVALS = {
    "Hourly": timedelta(hours=1),
    "Hourly Long": timedelta(hours=1),
    "Daily": timedelta(days=1),
    "Daily Long": timedelta(days=1),
    "Weekly": timedelta(weeks=1),
    "Weekly Long": timedelta(weeks=1),
    "Monthly": timedelta(days=30),
    "Monthly Long": timedelta(days=30),
    "Yearly": timedelta(days=365),
}


def _is_scheduled_trigger_due(trigger_row, now) -> bool:
    """First fire is always due (last_triggered_at is unset) — matches
    the old per-Scheduled-Job-Type behaviour where a freshly-created job
    fires on its first eligible tick rather than waiting a full interval."""
    last = get_datetime(trigger_row.last_triggered_at) if trigger_row.last_triggered_at else None

    if trigger_row.event_frequency == "Cron":
        if not trigger_row.cron_expression:
            return False
        from croniter import croniter
        from datetime import datetime as _datetime

        base = last or (now - timedelta(minutes=1))
        next_run = croniter(trigger_row.cron_expression, base).get_next(_datetime)
        return next_run <= now

    if last is None:
        return True
    interval = _FREQUENCY_INTERVALS.get(trigger_row.event_frequency, timedelta(days=1))
    return now - last >= interval


def run_scheduled_trigger_job(trigger_name: str, **kwargs):
    """Kept only for manual/console use (e.g. force-firing a specific
    trigger to test it, bypassing due-ness entirely) — nothing in the
    scheduler path calls this anymore. See run_due_scheduled_triggers
    above for the actual polling entrypoint."""
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

def _doc_info(context: dict) -> tuple:
    """(doctype, docname) of the triggering document, or (None, None)
    for scheduled/webhook/manual contexts that carry no doc."""
    doc_ctx = context.get("doc") if isinstance(context, dict) else None
    if isinstance(doc_ctx, dict):
        return doc_ctx.get("doctype"), doc_ctx.get("name")
    return None, None


def _notify_recipients(trigger, context: dict) -> list:
    """Who gets the OUTCOME notification: the user who performed the
    acting action (captured at fire time — inside the worker there is
    no request session to read it from), plus the trigger's run_as_user
    if set. Deduped; system accounts dropped."""
    users = []
    if isinstance(context, dict) and context.get("acting_user"):
        users.append(context["acting_user"])
    if trigger.get("run_as_user"):
        users.append(trigger.run_as_user)
    return dedupe_users(users)

def _notify_run_outcome(trigger, context: dict, result):
    """Persistent outcome signals for a finished triggered run.
 
    Bell notification goes to the user who performed the triggering
    action (captured at fire time) plus run_as_user if set. If nobody
    qualifies AND the run failed (unattended scheduled/webhook trigger
    with no run_as_user), fall back to System Managers so a failure is
    never silent — successful unattended runs notify no one.
 
    Doc comment goes on the triggering document, skipped for delete
    events (the doc may already be gone) and for non-doc contexts.
    Every channel here fails soft: a notification problem must never
    affect the run record that was already persisted.
    """
    success = result.ended_reason == "Completed"
    if not success:
        frappe.log_error(f"Triggered agent '{trigger.name}' ended with: {result.ended_reason}")
 
    doctype, docname = _doc_info(context)
    verb = "completed" if success else f"failed ({result.ended_reason})"
    subject = f"Agent '{trigger.trigger_name}' {verb}"
    if docname:
        subject += f" — {docname}"
 
    body = excerpt_text(result.response) if success else f"Run ended with: {result.ended_reason}"
 
    # Prefer linking the bell notification to the triggering document
    # itself (e.g. the BBS Schedule that fired this run) when the trigger
    # is doc-bound — that's what the user actually wants to open. Only
    # fall back to the Agent session when there's no doc context at all
    # (Scheduled/Webhook triggers with no doctype_name/docname), since
    # otherwise there'd be nothing sensible to link to.
    if trigger.get("doctype_name") and docname:
        link_doctype = trigger.doctype_name
        link_name = docname
    else:
        link_doctype = "Agent session"
        link_name = result.session_id
 
    recipients = _notify_recipients(trigger, context)
    if not recipients and not success:
        recipients = system_managers()
 
    for user in recipients:
        notify_run_complete(
            user=user,
            subject=subject,
            message=result.response if success else body,
            success=success,
            link_doctype=link_doctype,
            link_name=link_name,
        )
 
    # Contextual record: timeline comment on the doc that caused the
    # run. Comment is in _DOCTYPE_EVENT_DENYLIST, so this can never
    # re-fire a DocType Event trigger (no notification loops).
    event = context.get("event") if isinstance(context, dict) else None
    if doctype and docname and event not in ("on_trash", "after_delete"):
        add_agent_comment(
            doctype,
            docname,
            f"**🤖 {trigger.trigger_name} {verb}**\n\n{body}\n\n"
            f"[View run](/app/agent-session/{result.session_id})",
        )


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