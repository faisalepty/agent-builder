# agent_builder/agent_builder/page/agent_builder/agent_builder.py
"""Whitelisted read endpoints for the Agent Management Desk page.

Deliberately separate from verify.py — verify.py is the chat runtime
surface (send message, stream, stop); this module is the ops/observability
surface (browse sessions + lineage, browse workflow definitions, browse
workflow runs, resume paused runs).
"""
import json

import frappe
from frappe.utils import cint


@frappe.whitelist()
def get_sessions(limit=100):
    """Return top-level Agent Sessions (parent_session is empty) with each
    one's delegate children nested inline, so the frontend can render a
    call-stack tree without doing N+1 lookups per row.
    """
    is_admin = "System Manager" in frappe.get_roles(frappe.session.user)
    filters = {"parent_session": ["in", ["", None]]}
    if not is_admin:
        filters["user"] = frappe.session.user

    top_level = frappe.get_list(
        "Agent session",
        filters=filters,
        fields=[
            "name",
            "title",
            "user",
            "status",
            "ended_reason",
            "trigger_type",
            "trigger_source",
            "last_active",
            "turn_count",
            "tool_call_count",
            "total_input_tokens",
            "total_output_tokens",
            "estimated_cost",
            "delegate_depth",
        ],
        order_by="last_active desc",
        limit_page_length=int(limit),
        ignore_permissions=is_admin,
    )

    names = [s.name for s in top_level]
    children_by_parent = {}
    if names:
        children = frappe.get_list(
            "Agent session",
            filters={"parent_session": ["in", names]},
            fields=[
                "name",
                "title",
                "user",
                "status",
                "ended_reason",
                "trigger_type",
                "trigger_source",
                "parent_session",
                "delegated_skill",
                "delegate_depth",
                "last_active",
                "turn_count",
                "estimated_cost",
            ],
            order_by="last_active asc",
            ignore_permissions=True,
        )
        for c in children:
            children_by_parent.setdefault(c.parent_session, []).append(c)

    def attach(session):
        session["children"] = [attach(c) for c in children_by_parent.get(session["name"], [])]
        return session

    return [attach(s) for s in top_level]


@frappe.whitelist()
def get_available_tools():
    """All registered tool names, for the canvas's tool-step dropdown.

    Includes a synthetic 'trigger' entry — it's not executor-dispatched
    (engine.py's 'trigger' step type is declarative-only and is never
    passed to ToolExecutor), but it's listed here so it shows up
    consistently wherever tools are enumerated (this dropdown, an
    agent's own tool picker, etc.) rather than being invisible outside
    the workflow canvas's dedicated Trigger step button.
    """
    from agent_builder.native_api.agent.setup import get_tool_registry

    registry = get_tool_registry()
    names = sorted(registry.executors.keys())
    if "trigger" not in names:
        names.append("trigger")
    return names


@frappe.whitelist()
def get_tool_schemas():
    """Full JSON schema (name, description, parameters) for every tool,
    plus the same synthetic 'trigger' entry as get_available_tools.

    Robust against multiple shapes returned by
    `registry.get_tool_schemas()`:
      * list of OpenAI-wrapped: [{"type": "function", "function": {...}}, ...]
      * list of flat:           [{"name": ..., "description": ..., "parameters": ...}, ...]
      * dict mapping name → schema

    A single malformed entry (or a different storage convention than the
    caller assumed) used to raise KeyError here, 500-ing the whole
    endpoint. The JS wraps the call in `.catch(() => ({ message: [] }))`,
    so a 500 silently produced an empty list — which is why the sidebar
    showed "No schema loaded" for EVERY tool, not just one. Now each
    entry is normalized independently and any per-entry failure is
    logged without aborting the call.
    """
    from agent_builder.native_api.agent.setup import get_tool_registry

    def _normalize(entry):
        """Coerce a single raw schema entry to the flat shape the JS
        expects: {name, description, parameters}. Returns None if the
        entry can't be normalized (caller will fall back to a
        placeholder for that tool name)."""
        if not isinstance(entry, dict):
            return None
        # OpenAI-style wrapper: {"type": "function", "function": {...}}
        fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
        if not isinstance(fn, dict):
            return None
        name = fn.get("name")
        if not name:
            return None
        params = fn.get("parameters")
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        elif "properties" not in params:
            params = dict(params, properties={})
        return {
            "name": name,
            "description": fn.get("description") or "",
            "parameters": params,
        }

    registry = get_tool_registry()

    schema_by_name = {}
    try:
        raw = registry.get_tool_schemas() or []
        # dict form: {tool_name: schema_dict}
        if isinstance(raw, dict):
            items = []
            for k, v in raw.items():
                if isinstance(v, dict) and "name" not in v and "function" not in v:
                    v = dict(v, name=k)
                items.append(v)
        else:
            items = list(raw)

        for entry in items:
            norm = _normalize(entry)
            if norm:
                schema_by_name[norm["name"]] = norm
    except Exception:
        # Don't let a registry bug tank the whole picker — log it so
        # it's visible in Error Log, then fall through to placeholders.
        frappe.log_error(
            title="get_tool_schemas: registry.get_tool_schemas() failed",
            message=frappe.get_traceback(),
        )

    out = []
    for name in sorted(registry.executors.keys()):
        if name in schema_by_name:
            out.append(schema_by_name[name])
        else:
            out.append(
                {
                    "name": name,
                    "description": "(no schema registered for this tool — check its schema.py)",
                    "parameters": {"type": "object", "properties": {}},
                }
            )

    out.append(
        {
            "name": "trigger",
            "description": (
                "Declarative workflow entry point (DocType Event / Scheduled / "
                "Webhook / MCP). Not executable — defines what starts a workflow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger_kind": {
                        "type": "string",
                        "enum": ["doctype_event", "schedule", "webhook", "mcp"],
                    }
                },
            },
        }
    )
    return out


@frappe.whitelist()
def test_step(tool, args):
    """Dry-run a single tool call with user-supplied args and return the raw result."""
    import asyncio

    from agent_builder.native_api.agent.setup import get_tool_registry
    from agent_builder.native_api.tools.executor import ToolExecutor

    parsed_args = args
    if isinstance(args, str):
        try:
            parsed_args = frappe.parse_json(args)
        except Exception:
            # Not valid JSON (e.g. a Jinja template like "{{output}}").
            # Pass the raw string to the executor — the executor will
            # handle it or fail gracefully.
            parsed_args = args

    executor = ToolExecutor(get_tool_registry())
    raw = asyncio.run(executor._dispatch(tool, frappe.as_json(parsed_args)))
    try:
        return {"output": frappe.parse_json(raw)}
    except Exception:
        return {"output": raw}


# =========================================================================
# Tools section — global enable/disable, grouped by Tool Group.
#
# This controls what's *offered* to every agent's model (see
# setup.py::get_tool_schemas_for's global filter layer), independent of
# any single Agent Definition's own tool_mode/allowed_tools. It does not
# affect what ToolExecutor can dispatch — see tool_sync.py's module
# docstring for why that's an intentional v1 scope, not an oversight.
# =========================================================================


@frappe.whitelist()
def get_tool_groups():
    """Grouped view for the Tools section: every Tool Group with its
    child Agent Tool rows nested inline, so the frontend can render the
    collapsible list in one call."""
    groups = frappe.get_all(
        "Tool Group",
        fields=["name", "group_name", "is_enabled", "is_orphaned", "description"],
        order_by="group_name asc",
    )
    tools = frappe.get_all(
        "Agent Tool",
        fields=["name", "tool_name", "tool_group", "is_enabled", "is_orphaned", "description"],
        order_by="tool_name asc",
    )
    tools_by_group: dict[str, list] = {}
    for t in tools:
        tools_by_group.setdefault(t["tool_group"], []).append(t)

    for g in groups:
        g["tools"] = tools_by_group.get(g["group_name"], [])
    return groups


@frappe.whitelist()
def set_tool_group_enabled(group_name: str, is_enabled):
    """Toggle a whole group. Does not touch the individual is_enabled
    value stored on the tools inside it — see tool_sync.py docstring."""
    frappe.only_for("System Manager")
    frappe.db.set_value("Tool Group", group_name, "is_enabled", cint(is_enabled))
    frappe.db.commit()


@frappe.whitelist()
def set_tool_enabled(tool_name: str, is_enabled):
    frappe.only_for("System Manager")
    frappe.db.set_value("Agent Tool", tool_name, "is_enabled", cint(is_enabled))
    frappe.db.commit()


@frappe.whitelist()
def resync_tools():
    """'Sync Tools' button — pick up new/removed tool files without a
    worker restart."""
    from agent_builder.native_api.tools.tool_sync import resync_tools as _resync

    return _resync()


@frappe.whitelist()
def delete_orphaned_tools(doctype: str):
    """Deliberate cleanup of rows flagged orphaned by the last sync."""
    from agent_builder.native_api.tools.tool_sync import delete_orphaned

    return delete_orphaned(doctype)


@frappe.whitelist()
def get_agent_skills():
    """Skills marked is_agent=1 — the picker list for delegate_task steps."""
    frappe.log_error(frappe.get_all(
        "Skill",
        filters={"is_agent": 1, "is_enabled": 1},
        fields=["name", "name_", "description"],
        order_by="name asc",
    ))
    return frappe.get_all(
        "Skill",
        filters={"is_agent": 1, "is_enabled": 1},
        fields=["name", "name_", "description"],
        order_by="name asc",
    )


@frappe.whitelist()
def get_workflow(workflow_name):
    wf = frappe.get_doc("Agent Workflow", workflow_name)
    return {
        "workflow_name": wf.workflow_name,
        "description": wf.description,
        "is_enabled": wf.is_enabled,
        "error_workflow": wf.get("error_workflow"),
        "steps": frappe.parse_json(wf.steps) if wf.steps else [],
    }


@frappe.whitelist()
def get_workflow_names():
    """Slim list of enabled workflow names — for populating the 'workflow'
    step type's picker (sub-workflow calls) and the error_workflow field,
    without pulling full step JSON for every row like get_workflows() does.
    """
    return frappe.get_all(
        "Agent Workflow",
        filters={"is_enabled": 1},
        fields=["name", "workflow_name", "description"],
        order_by="workflow_name asc",
    )


@frappe.whitelist()
def create_workflow(workflow_name, description=None):
    """Create a new, empty Agent Workflow and return its docname."""
    workflow_name = (workflow_name or "").strip()
    if not workflow_name:
        frappe.throw("Workflow name is required.")

    doc = frappe.new_doc("Agent Workflow")
    doc.workflow_name = workflow_name
    doc.description = description or ""
    doc.is_enabled = 1
    doc.steps = "[]"
    doc.insert()
    frappe.db.commit()

    return {"name": doc.name, "workflow_name": doc.workflow_name}


@frappe.whitelist()
def save_workflow_steps(workflow_name, steps):
    """Overwrite the full steps array in one call, and sync every
    'trigger' step to its own Agent Trigger record — see
    _sync_trigger_steps. There is no separate 'save this trigger'
    action anywhere: saving the workflow is saving its triggers.
    """
    steps_parsed = frappe.parse_json(steps) if isinstance(steps, str) else steps
    ids = [s.get("id") for s in steps_parsed]
    if len(ids) != len(set(ids)):
        frappe.throw("Duplicate step ids found — each step must have a unique id.")

    frappe.db.set_value(
        "Agent Workflow",
        workflow_name,
        "steps",
        frappe.as_json(steps_parsed),
    )

    webhook_tokens = _sync_trigger_steps(workflow_name, steps_parsed)

    frappe.db.commit()
    return {"status": "saved", "step_count": len(steps_parsed), "webhook_tokens": webhook_tokens}


def _sync_trigger_steps(workflow_name, steps):
    """Each 'trigger' step on the canvas IS an Agent Trigger record,
    1:1, named after the step's own id (Agent Trigger autonames by
    trigger_name — using the step id directly means the link is
    implicit, no separate 'agent_trigger' reference field needed, and
    no separate picker/save UI on the node).

    Scheduled-type triggers no longer get a per-trigger `Scheduled Job
    Type` record — see run_due_scheduled_triggers in trigger.py, which
    polls all enabled Scheduled triggers from one static job instead
    (core Frappe can't pass per-record arguments into a scheduled job's
    callback, so one job per trigger silently could never work). The
    stale-cleanup below still deletes any leftover `agent_trigger::*`
    Scheduled Job Type rows from the old per-trigger design if found.

    Returns {step_id: webhook_token} for any Webhook-type triggers,
    so the frontend can display the server-generated token without a
    second round trip.
    """
    from agent_builder.native_api.trigger import invalidate_trigger_cache

    current_trigger_ids = {step["id"] for step in steps if step.get("type") == "trigger"}
    existing_trigger_ids = frappe.get_all(
        "Agent Trigger", filters={"workflow_name": workflow_name}, pluck="name"
    )
    stale_ids = set(existing_trigger_ids) - current_trigger_ids
    for stale_name in stale_ids:
        frappe.db.delete("Scheduled Job Type", {"name": f"agent_trigger::{stale_name}"})
        frappe.delete_doc("Agent Trigger", stale_name, ignore_permissions=True)

    webhook_tokens = {}
    for step in steps:
        if step.get("type") != "trigger":
            continue

        trigger_docname = step["id"]
        fields = {
            "trigger_name": trigger_docname,
            "is_enabled": 1 if step.get("is_enabled", True) else 0,
            "workflow_name": workflow_name,
            "trigger_type": step.get("trigger_type") or "DocType Event",
            "doctype_name": step.get("doctype_name") or None,
            "doctype_event": step.get("doctype_event") or None,
            "event_frequency": step.get("event_frequency") or "Daily",
            "cron_expression": step.get("cron_expression") or None,
            "run_as_user": step.get("run_as_user") or "Administrator",
            "input_template": step.get("input_template") or "",
            "condition": step.get("condition") or None,
        }

        if frappe.db.exists("Agent Trigger", trigger_docname):
            doc = frappe.get_doc("Agent Trigger", trigger_docname)
            doc.update(fields)
        else:
            doc = frappe.get_doc({"doctype": "Agent Trigger", **fields})

        doc.save(ignore_permissions=True)

        if doc.trigger_type == "Webhook":
            webhook_tokens[trigger_docname] = doc.webhook_token

    # One invalidation covering both the stale deletions above and every
    # create/update in the loop, rather than one call per trigger step.
    if stale_ids or current_trigger_ids:
        invalidate_trigger_cache()

    return webhook_tokens


@frappe.whitelist()
def search_doctypes(txt=""):
    """Lightweight DocType name search for the Trigger node's 'DocType'
    field — a plain text input with autocomplete rather than a full
    Frappe Link control, since this sidebar isn't a real Frappe form.
    """
    return frappe.get_all(
        "DocType",
        filters={"name": ["like", f"%{txt}%"]},
        fields=["name"],
        order_by="name asc",
        limit_page_length=20,
        pluck="name",
    )


@frappe.whitelist()
def set_error_workflow(workflow_name, error_workflow=None):
    """Point a workflow at another workflow to run on failure. Pass
    error_workflow=None (or omit) to clear it.

    NOTE: requires an 'error_workflow' Link(Agent Workflow) field added
    to the Agent Workflow doctype itself — this endpoint assumes that
    field exists; add it via the doctype's field list if it isn't there
    yet, since this Desk page module doesn't own that doctype's schema.
    """
    frappe.db.set_value("Agent Workflow", workflow_name, "error_workflow", error_workflow)
    frappe.db.commit()
    return {"status": "saved", "error_workflow": error_workflow}


@frappe.whitelist()
def get_workflows():
    """List Agent Workflow definitions — metadata only, no step contents."""
    workflows = frappe.get_all(
        "Agent Workflow",
        fields=["name", "workflow_name", "description", "is_enabled", "modified", "steps"],
        order_by="modified desc",
    )
    for wf in workflows:
        try:
            wf["step_count"] = len(frappe.parse_json(wf.pop("steps")) or [])
        except Exception:
            wf.pop("steps", None)
            wf["step_count"] = 0
    return workflows


@frappe.whitelist()
def get_workflow_runs(workflow_name=None, limit=50):
    """List Agent Workflow Run records — the execution-history view.
    Filter by workflow_name, or omit it to see runs across all workflows.
    """
    filters = {}
    if workflow_name:
        filters["workflow"] = workflow_name

    is_admin = "System Manager" in frappe.get_roles(frappe.session.user)

    return frappe.get_list(
        "Agent Workflow Run",
        filters=filters,
        fields=[
            "name",
            "workflow",
            "status",
            "trigger_source",
            "started_at",
            "finished_at",
            "paused_step",
            "error",
        ],
        order_by="started_at desc",
        limit_page_length=int(limit),
        ignore_permissions=is_admin,
    )


@frappe.whitelist()
def get_workflow_run(run_name):
    """Full detail for one run — parsed log + final_output, for the
    canvas's run-overlay (per-step status/output) and the human_approval
    review screen.
    """
    run = frappe.get_doc("Agent Workflow Run", run_name)
    return {
        "name": run.name,
        "workflow": run.workflow,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "paused_step": run.paused_step,
        "error": run.error,
        "log": frappe.parse_json(run.log) if run.log else [],
        "final_output": frappe.parse_json(run.final_output) if run.final_output else None,
    }


@frappe.whitelist()
def resume_workflow(run_name, decision, edited_output=None):
    """Approve or reject a run paused at a human_approval step.

    decision: "approve" | "reject"
    edited_output: optional JSON string/dict to replace the paused
    output before the run continues (approve only).
    """
    from agent_builder.native_api.workflow.engine import resume_workflow as _resume

    parsed_output = frappe.parse_json(edited_output) if isinstance(edited_output, str) else edited_output
    return _resume(run_name, decision, edited_output=parsed_output)


@frappe.whitelist()
def get_triggers():
    """List Agent Trigger records."""
    return frappe.get_list(
        "Agent Trigger",
        fields=[
            "trigger_name",
            "workflow_name",
            "agent_name",
            "trigger_type",
            "doctype_name",
            "doctype_event",
            "event_frequency",
            "cron_expression",
            "input_template",
            "is_enabled",
        ],
        order_by="modified desc",
    )


def _build_trigger_fields(data):
    """Shared validation for create_trigger and update_trigger, so both
    paths produce identical, correctly-validated Agent Trigger field
    sets."""
    target_type = data.get("target_type") or "Workflow"
    trigger_type = data.get("trigger_type")
    if trigger_type not in ("DocType Event", "Scheduled", "Webhook"):
        frappe.throw(f"Invalid trigger_type: {trigger_type}")

    fields = {
        "trigger_type": trigger_type,
        "run_as_user": data.get("run_as_user") or "Administrator",
        # Clear fields not relevant to the new type/target on every save,
        # so switching e.g. Scheduled -> Webhook doesn't leave a stale
        # cron_expression lying around that run_due_scheduled_triggers or
        # a future edit could accidentally pick back up.
        "agent_name": None,
        "workflow_name": None,
        "doctype_name": None,
        "doctype_event": None,
        "event_frequency": None,
        "cron_expression": None,
    }

    if target_type == "Agent":
        if not data.get("agent_name"):
            frappe.throw("agent_name is required when target_type is 'Agent'")
        if not data.get("input_template"):
            frappe.throw("input_template is required when target_type is 'Agent' — it becomes the agent's first message.")
        fields["agent_name"] = data["agent_name"]
        fields["input_template"] = data["input_template"]
    else:
        if not data.get("workflow_name"):
            frappe.throw("workflow_name is required when target_type is 'Workflow'")
        fields["workflow_name"] = data["workflow_name"]
        fields["input_template"] = data.get("input_template") or ""

    if trigger_type == "DocType Event":
        if not data.get("doctype_name") or not data.get("doctype_event"):
            frappe.throw("doctype_name and doctype_event are required for a DocType Event trigger")
        fields["doctype_name"] = data["doctype_name"]
        fields["doctype_event"] = data["doctype_event"]

    elif trigger_type == "Scheduled":
        event_frequency = data.get("event_frequency") or "Daily"
        valid_frequencies = ("Hourly", "Daily", "Weekly", "Monthly", "Yearly",
                              "Hourly Long", "Daily Long", "Weekly Long", "Monthly Long", "Cron")
        if event_frequency not in valid_frequencies:
            frappe.throw(f"Invalid event_frequency: {event_frequency}")
        fields["event_frequency"] = event_frequency

        if event_frequency == "Cron":
            cron_expression = data.get("cron_expression")
            if not cron_expression:
                frappe.throw("cron_expression is required when event_frequency is 'Cron'")
            try:
                import croniter
                croniter.croniter(cron_expression)
            except Exception:
                frappe.throw(f"Invalid cron expression: {cron_expression}")
            fields["cron_expression"] = cron_expression

    return fields


@frappe.whitelist()
def create_trigger(trigger_data):
    """Create a standalone Agent Trigger — this is the Trigger tab's entry
    point (agent_builder.js: createTrigger), separate from the canvas's
    1:1 trigger-step sync (_sync_trigger_steps above). Both write the same
    Agent Trigger schema, so a Scheduled trigger fires the same way (via
    trigger.py's run_due_scheduled_triggers polling job) regardless of
    which UI made it.

    trigger_data (from the frontend dialog):
      {
        trigger_name: str,
        target_type: "Workflow" | "Agent",
        workflow_name: str,   # if target_type == "Workflow"
        agent_name: str,      # if target_type == "Agent"
        trigger_type: "DocType Event" | "Scheduled" | "Webhook",
        doctype_name: str,    # if trigger_type == "DocType Event"
        doctype_event: str,   # if trigger_type == "DocType Event"
        event_frequency: str, # if trigger_type == "Scheduled"
        cron_expression: str, # if trigger_type == "Scheduled" and event_frequency == "Cron"
      }
    """
    data = json.loads(trigger_data) if isinstance(trigger_data, str) else trigger_data

    fields = _build_trigger_fields(data)
    fields["trigger_name"] = data.get("trigger_name")
    fields["is_enabled"] = 1

    doc = frappe.get_doc({"doctype": "Agent Trigger", **fields})
    doc.insert()

    from agent_builder.native_api.trigger import invalidate_trigger_cache
    invalidate_trigger_cache()

    frappe.db.commit()
    return {"name": doc.name, "webhook_token": doc.get("webhook_token")}


@frappe.whitelist()
def update_trigger(trigger_name, trigger_data):
    """Edit an existing standalone Agent Trigger — same field set/
    validation as create_trigger, but updates in place. A changed cron/
    frequency takes effect on the next run_due_scheduled_triggers tick
    automatically since that job reads Agent Trigger fresh each time —
    no separate re-sync step needed.
    trigger_name itself isn't editable here (it's the doc's autoname key).
    """
    data = json.loads(trigger_data) if isinstance(trigger_data, str) else trigger_data

    doc = frappe.get_doc("Agent Trigger", trigger_name)
    fields = _build_trigger_fields(data)
    doc.update(fields)
    doc.save(ignore_permissions=True)

    from agent_builder.native_api.trigger import invalidate_trigger_cache
    invalidate_trigger_cache()

    frappe.db.commit()
    return {"name": doc.name, "webhook_token": doc.get("webhook_token")}


@frappe.whitelist()
def toggle_trigger(trigger_name, enabled):
    is_enabled = 1 if str(enabled).lower() in ("1", "true") else 0
    doc = frappe.get_doc("Agent Trigger", trigger_name)
    doc.is_enabled = is_enabled
    doc.save(ignore_permissions=True)

    # Disabling a Scheduled trigger is enough on its own now —
    # run_due_scheduled_triggers filters on is_enabled=1 every tick, so
    # there's no separate Scheduled Job Type to stop in sync here.
    from agent_builder.native_api.trigger import invalidate_trigger_cache
    invalidate_trigger_cache()

    frappe.db.commit()


@frappe.whitelist()
def delete_trigger(trigger_name):
    # Leftover cleanup only — no code creates agent_trigger::* Scheduled
    # Job Type rows anymore, but this is harmless (no-op) if none exist,
    # and clears out any still-orphaned row from the old per-trigger
    # design if this trigger predates the switch to run_due_scheduled_triggers.
    frappe.db.delete("Scheduled Job Type", {"name": f"agent_trigger::{trigger_name}"})
    frappe.delete_doc("Agent Trigger", trigger_name)

    from agent_builder.native_api.trigger import invalidate_trigger_cache
    invalidate_trigger_cache()

    frappe.db.commit()


@frappe.whitelist()
def toggle_workflow(workflow_name, enabled):
    frappe.db.set_value("Agent Workflow", workflow_name, "is_enabled", enabled)
    frappe.db.commit()


@frappe.whitelist()
def execute_workflow(workflow_name, input_data):
    """Execute the workflow synchronously and return the result.

    Running synchronously is better for testing in the UI because any
    errors are immediately thrown back to the user, and the final output
    can be viewed directly. If the run pauses at a human_approval step,
    the returned result's status will be "Paused" with a run_name to
    resume later via resume_workflow — this call does NOT throw in that
    case, since pausing isn't a failure.
    """
    parsed_input = json.loads(input_data) if isinstance(input_data, str) else (input_data or {})

    try:
        from agent_builder.native_api.workflow.engine import run_workflow
        result = run_workflow(workflow_name=workflow_name, initial_input=parsed_input)
        return {"success": True, "result": result}
    except Exception as e:
        frappe.log_error(title=f"Workflow Execution Failed: {workflow_name}", message=frappe.get_traceback())
        frappe.throw(f"Workflow execution failed: {str(e)}")