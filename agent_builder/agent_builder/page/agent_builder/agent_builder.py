# agent_builder/agent_builder/page/agent_builder/agent_builder.py
"""Whitelisted read endpoints for the Agent Management Desk page.

Deliberately separate from verify.py — verify.py is the chat runtime
surface (send message, stream, stop); this module is the ops/observability
surface (browse sessions + lineage, browse workflow definitions, browse
workflow runs, resume paused runs).
"""
import json

import frappe


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
    plus the same synthetic 'trigger' entry as get_available_tools."""
    from agent_builder.native_api.agent.setup import get_tool_registry

    registry = get_tool_registry()
    schema_by_name = {s["function"]["name"]: s["function"] for s in registry.get_tool_schemas()}

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

    parsed_args = frappe.parse_json(args) if isinstance(args, str) else (args or {})
    executor = ToolExecutor(get_tool_registry())
    raw = asyncio.run(executor._dispatch(tool, frappe.as_json(parsed_args)))
    try:
        return {"output": frappe.parse_json(raw)}
    except Exception:
        return {"output": raw}


@frappe.whitelist()
def get_agent_skills():
    """Skills marked is_agent=1 — the picker list for delegate_task steps."""
    return frappe.get_all(
        "Skill",
        filters={"is_agent": 1, "is_enabled": 1},
        fields=["name", "description"],
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
    """Overwrite the full steps array in one call."""
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
    frappe.db.commit()
    return {"status": "saved", "step_count": len(steps_parsed)}


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
def get_workflow_triggers(workflow_name):
    """Agent Trigger records already targeting this workflow — populates
    the Trigger node sidebar's 'existing triggers' picker.
    """
    return frappe.get_all(
        "Agent Trigger",
        filters={"workflow_name": workflow_name},
        fields=[
            "name",
            "trigger_name",
            "is_enabled",
            "trigger_type",
            "doctype_name",
            "doctype_event",
            "cron_expression",
            "webhook_token",
            "run_as_user",
            "input_template",
            "condition",
        ],
        order_by="modified desc",
    )


@frappe.whitelist()
def get_trigger(trigger_name):
    """Full detail for one Agent Trigger — used when the sidebar switches
    from the picker into edit mode for an existing record.
    """
    doc = frappe.get_doc("Agent Trigger", trigger_name)
    return {
        "name": doc.name,
        "trigger_name": doc.trigger_name,
        "is_enabled": doc.is_enabled,
        "agent_name": doc.agent_name,
        "workflow_name": doc.workflow_name,
        "run_as_user": doc.run_as_user,
        "trigger_type": doc.trigger_type,
        "doctype_name": doc.doctype_name,
        "doctype_event": doc.doctype_event,
        "cron_expression": doc.cron_expression,
        "webhook_token": doc.webhook_token,
        "input_template": doc.input_template,
        "condition": doc.condition,
    }


@frappe.whitelist()
def save_workflow_trigger(workflow_name, trigger_data):
    """Create or update an Agent Trigger targeting this workflow, from the
    canvas's Trigger node sidebar. trigger_data.name (if present) means
    "update this existing record"; otherwise a new one is created.

    workflow_name is always force-set here — the Trigger node lives on
    one specific workflow's canvas, so there's no scenario where the
    sidebar should be allowed to silently repoint an existing trigger at
    a different workflow.
    """
    data = frappe.parse_json(trigger_data) if isinstance(trigger_data, str) else (trigger_data or {})
    data["workflow_name"] = workflow_name
    # agent_name is irrelevant on a workflow-targeted trigger (fire_trigger
    # ignores it once workflow_name is set) — don't let a stray leftover
    # value confuse the Agent Trigger list view.
    data.pop("agent_name", None)

    existing_name = data.pop("name", None)
    if existing_name and frappe.db.exists("Agent Trigger", existing_name):
        doc = frappe.get_doc("Agent Trigger", existing_name)
        doc.update(data)
    else:
        doc = frappe.get_doc({"doctype": "Agent Trigger", **data})

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": doc.name,
        "trigger_name": doc.trigger_name,
        "trigger_type": doc.trigger_type,
        "webhook_token": doc.webhook_token,
    }


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
def get_triggers():
    """List Agent Trigger records."""
    return frappe.get_list(
        "Agent Trigger",
        fields=[
            "name",
            "workflow_name",
            "trigger_type",
            "doctype_name",
            "doctype_event",
            "cron_expression",
            "is_enabled",
        ],
        order_by="modified desc",
    )


@frappe.whitelist()
def create_trigger(trigger_data):
    data = json.loads(trigger_data) if isinstance(trigger_data, str) else trigger_data
    doc = frappe.get_doc({
        "doctype": "Agent Trigger",
        **data,
    })
    doc.insert()
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def toggle_trigger(trigger_name, enabled):
    frappe.db.set_value("Agent Trigger", trigger_name, "is_enabled", enabled)
    frappe.db.commit()


@frappe.whitelist()
def delete_trigger(trigger_name):
    frappe.delete_doc("Agent Trigger", trigger_name)
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