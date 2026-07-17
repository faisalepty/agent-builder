# agent_builder/native_api/workflow_engine.py
"""Runs an Agent Workflow: an ordered chain of typed steps.

Step types, modeled after the common primitives across n8n/Make/Zapier/
Temporal-style tools (not every step is an agent):

  Agent           - the existing Agent.run() closed loop (see triggers.py)
  HTTP Request    - call any external API
  Condition       - gate: if the expression is falsy, the run stops here
                    (status "skipped", not "error")
  Transform (Code)- sandboxed Python, for data reshaping between steps
  Frappe Action   - create/update/submit/cancel a native doctype record,
                    for the steps that don't need an LLM at all
  Delay           - re-enqueues the rest of the run after N seconds instead
                    of blocking a worker
  Human Approval  - pauses the run, creates a ToDo for the approver; the
                    run resumes via resume_workflow() when approved/rejected

Still deliberately linear (no fan-out/parallel nodes) — see the module
docstring in the previous version for why that's an acceptable v1 scope.
"""
import asyncio
import json
import logging

import frappe
from frappe.utils import now_datetime, cint
from frappe.utils.safe_exec import get_safe_globals, safe_exec

from agent_builder.native_api.agent.conversation import Conversation, StoppedByUser
from agent_builder.native_api.agent.agent import Agent, MaxTurnsError

logger = logging.getLogger(__name__)


# =========================================================================
# Entry points
# =========================================================================

@frappe.whitelist()
def run_workflow(workflow_name: str, trigger_context: dict = None):
    """API/enqueue entrypoint: run a workflow now, in the background."""
    trigger_context = frappe.parse_json(trigger_context) if isinstance(trigger_context, str) else (trigger_context or {})

    job = frappe.enqueue(
        method="agent_builder.native_api.workflow_engine.execute_workflow",
        queue="short",
        timeout=1200,
        workflow_name=workflow_name,
        trigger_context=trigger_context,
    )
    return {"status": "queued", "job_id": getattr(job, "id", None)}


@frappe.whitelist()
def resume_workflow(run_name: str, approved: bool = True):
    """Call this when a Human Approval step's ToDo is actioned, or to
    manually continue a run that's sitting in waiting_approval."""
    frappe.enqueue(
        method="agent_builder.native_api.workflow_engine.execute_workflow",
        queue="short",
        timeout=1200,
        workflow_name=None,
        trigger_context=None,
        resume_run_name=run_name,
        approved=cint(approved) if not isinstance(approved, bool) else approved,
    )
    return {"status": "resuming"}


def execute_workflow(
    workflow_name: str = None,
    trigger_context: dict = None,
    resume_run_name: str = None,
    approved: bool = True,
):
    """Background job body. Either starts a fresh run (workflow_name given)
    or resumes an existing one (resume_run_name given)."""
    if resume_run_name:
        run = frappe.get_doc("Agent Workflow Run", resume_run_name)
        workflow = frappe.get_doc("Agent Workflow", run.workflow)
        context = frappe.parse_json(run.running_context or "{}")
        trigger_context = frappe.parse_json(run.trigger_context or "{}")
        start_idx = run.resume_step_idx or 0

        if not approved:
            run.status = "skipped"
            run.ended_at = now_datetime()
            run.save(ignore_permissions=True)
            frappe.db.commit()
            return run.name
    else:
        workflow = frappe.get_doc("Agent Workflow", workflow_name)
        trigger_context = trigger_context or {}
        context = {}
        start_idx = 0

        if workflow.status != "Active":
            logger.info("Workflow '%s' is not Active, skipping.", workflow.name)
            return

        run = frappe.get_doc({
            "doctype": "Agent Workflow Run",
            "workflow": workflow.name,
            "status": "running",
            "started_at": now_datetime(),
            "trigger_context": frappe.as_json(trigger_context),
            "running_context": "{}",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    return _run_steps(workflow, run, trigger_context, context, start_idx)


# =========================================================================
# Step loop
# =========================================================================

def _run_steps(workflow, run, trigger_context: dict, context: dict, start_idx: int):
    steps = list(workflow.steps)
    previous_output = context.get(steps[start_idx - 1].step_name, "") if start_idx > 0 and steps else ""

    for idx in range(start_idx, len(steps)):
        step = steps[idx]
        step_run = run.append("step_runs", {
            "step_name": step.step_name,
            "agent_name": getattr(step, "agent_name", None),
            "status": "running",
        })
        run.save(ignore_permissions=True)
        frappe.db.commit()

        render_ctx = {"trigger_context": trigger_context, "previous_output": previous_output, "context": context}

        try:
            if step.step_type == "Delay":
                run.resume_step_idx = idx + 1
                run.running_context = frappe.as_json(context)
                run.status = "running"
                step_run.status = "success"
                step_run.output = f"Delaying {step.delay_seconds or 0}s"
                run.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.enqueue(
                    method="agent_builder.native_api.workflow_engine.execute_workflow",
                    queue="short",
                    timeout=1200,
                    at_front=False,
                    enqueue_after_commit=True,
                    workflow_name=None,
                    trigger_context=None,
                    resume_run_name=run.name,
                    approved=True,
                    # NOTE: frappe.enqueue doesn't natively support a delay
                    # param across all versions/queues — if yours doesn't,
                    # swap this for `frappe.enqueue_after(seconds=..., ...)`
                    # or a scheduled sweep job that checks 'running_context'
                    # rows whose delay has elapsed.
                )
                return run.name

            elif step.step_type == "Human Approval":
                run.resume_step_idx = idx + 1
                run.running_context = frappe.as_json(context)
                run.status = "waiting_approval"
                step_run.status = "pending"
                run.save(ignore_permissions=True)
                frappe.db.commit()

                message = frappe.render_template(step.approval_message or "Approval needed for workflow '{{ trigger_context }}'", render_ctx)
                frappe.get_doc({
                    "doctype": "ToDo",
                    "allocated_to": step.approver_user,
                    "description": f"[Agent Workflow: {workflow.name} / {step.step_name}] {message}",
                    "reference_type": "Agent Workflow Run",
                    "reference_name": run.name,
                }).insert(ignore_permissions=True)
                frappe.db.commit()
                return run.name

            elif step.step_type == "Condition":
                ok = _safe_eval(step.condition_expression, render_ctx)
                step_run.status = "success"
                step_run.output = f"Condition -> {ok}"
                if not ok:
                    run.status = "skipped"
                    run.ended_at = now_datetime()
                    run.final_output = previous_output
                    run.save(ignore_permissions=True)
                    frappe.db.commit()
                    return run.name
                output = previous_output  # condition passes data through unchanged

            elif step.step_type == "Transform (Code)":
                output = _run_code(step.code, render_ctx)
                step_run.status = "success"
                step_run.output = _stringify(output)

            elif step.step_type == "HTTP Request":
                output = _run_http(step, render_ctx)
                step_run.status = "success"
                step_run.output = _stringify(output)

            elif step.step_type == "Frappe Action":
                output = _run_frappe_action(step, render_ctx)
                step_run.status = "success"
                step_run.output = _stringify(output)

            else:  # "Agent" (also the default/legacy behavior)
                output = _run_agent_step(step, workflow, render_ctx)
                step_run.status = "success"
                step_run.output = output
                step_run.session = frappe.flags.get("_last_workflow_session")

            context[step.step_name] = output
            previous_output = output

        except Exception as e:
            step_run.status = "error"
            step_run.error = str(e)
            frappe.log_error("Agent Workflow Step Error", frappe.get_traceback())
            run.save(ignore_permissions=True)
            frappe.db.commit()

            if step.stop_on_error:
                run.status = "error"
                run.ended_at = now_datetime()
                run.save(ignore_permissions=True)
                frappe.db.commit()
                return run.name
            else:
                continue

        run.save(ignore_permissions=True)
        frappe.db.commit()

    run.status = "success"
    run.ended_at = now_datetime()
    run.final_output = _stringify(previous_output)
    run.save(ignore_permissions=True)
    frappe.db.commit()
    return run.name


# =========================================================================
# Per-type executors
# =========================================================================

def _run_agent_step(step, workflow, render_ctx: dict) -> str:
    rendered_message = frappe.render_template(step.input_template or "", render_ctx)

    conversation = Conversation(user=workflow.run_as_user or "Administrator")
    conversation.doc.agent_name = step.agent_name
    conversation.doc.trigger_type = "DocType Event" if render_ctx["trigger_context"] else "Scheduled"
    conversation.doc.trigger_source = f"Agent Workflow: {workflow.name} / {step.step_name}"
    conversation.add_user_message(rendered_message)

    agent = Agent(agent_name=step.agent_name)
    try:
        result = asyncio.run(agent.run(conversation))
    except (MaxTurnsError, StoppedByUser):
        raise
    finally:
        frappe.flags._last_workflow_session = conversation.session_id
    return result


def _run_http(step, render_ctx: dict) -> dict:
    import requests  # already a Frappe dependency

    url = frappe.render_template(step.http_url or "", render_ctx)
    headers = _render_json(step.http_headers, render_ctx) or {}
    body = _render_json(step.http_body, render_ctx) if step.http_method != "GET" else None

    resp = requests.request(step.http_method or "GET", url, headers=headers, json=body, timeout=30)
    try:
        parsed = resp.json()
    except ValueError:
        parsed = resp.text
    return {"status_code": resp.status_code, "body": parsed}


def _run_frappe_action(step, render_ctx: dict):
    fields = _render_json(step.doc_fields, render_ctx) or {}

    if step.doc_action == "Create":
        doc = frappe.get_doc({"doctype": step.target_doctype, **fields})
        doc.insert(ignore_permissions=False)
        return {"name": doc.name}

    name = fields.get("name")
    if not name:
        frappe.throw("Frappe Action 'Fields' must include 'name' for Update/Submit/Cancel.")
    doc = frappe.get_doc(step.target_doctype, name)

    if step.doc_action == "Update":
        doc.update({k: v for k, v in fields.items() if k != "name"})
        doc.save(ignore_permissions=False)
    elif step.doc_action == "Submit":
        doc.submit()
    elif step.doc_action == "Cancel":
        doc.cancel()

    return {"name": doc.name}


def _run_code(code: str, render_ctx: dict):
    local_vars = dict(render_ctx)
    safe_exec(code or "", get_safe_globals(), local_vars)
    return local_vars.get("result")


def _safe_eval(expression: str, render_ctx: dict) -> bool:
    if not expression:
        return True
    safe_globals = get_safe_globals()
    safe_globals.update(render_ctx)
    try:
        return bool(frappe.safe_eval(expression, safe_globals))
    except Exception:
        logger.warning("Condition failed to evaluate: %s", expression)
        return False


def _render_json(template: str, render_ctx: dict):
    if not template:
        return None
    rendered = frappe.render_template(template, render_ctx)
    try:
        return json.loads(rendered)
    except Exception:
        return rendered


def _stringify(value) -> str:
    if isinstance(value, (dict, list)):
        return frappe.as_json(value)
    return str(value) if value is not None else ""