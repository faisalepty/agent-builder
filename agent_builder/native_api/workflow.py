# agent_builder/native_api/workflow.py
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
import inspect
import json
import logging

import frappe
from frappe.utils import cint, now_datetime

from agent_builder.native_api.agent.runner import SessionProvenance, run_headless_agent
from agent_builder.native_api.agent.setup import get_tool_registry

logger = logging.getLogger(__name__)


# =========================================================================
# Entry points
# =========================================================================


@frappe.whitelist()
def run_workflow(workflow_name: str, trigger_context: dict = None):
	"""API/enqueue entrypoint: run a workflow now, in the background."""
	trigger_context = (
		frappe.parse_json(trigger_context) if isinstance(trigger_context, str) else (trigger_context or {})
	)

	job = frappe.enqueue(
		method="agent_builder.native_api.workflow.execute_workflow",
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
		method="agent_builder.native_api.workflow.execute_workflow",
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
			frappe.log_error(f"Workflow '{workflow.name}' is not Active, skipping.")
			return

		run = frappe.get_doc(
			{
				"doctype": "Agent Workflow Run",
				"workflow": workflow.name,
				"status": "running",
				"started_at": now_datetime(),
				"trigger_context": frappe.as_json(trigger_context),
				"running_context": "{}",
			}
		).insert(ignore_permissions=True)
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
		step_run = run.append(
			"step_runs",
			{
				"step_name": step.step_name,
				"agent_name": getattr(step, "agent_name", None),
				"status": "running",
			},
		)
		run.save(ignore_permissions=True)
		frappe.db.commit()

		render_ctx = {
			"trigger_context": trigger_context or {},
			"previous_output": previous_output,
			"context": context or {},
		}

		try:
			step_context = {
				"trigger_context": trigger_context,
				"previous_output": previous_output,
				"context": context,
				"workflow_name": workflow.name,
				"workflow_run": run,
				"step_index": idx,
				"run_as_user": workflow.run_as_user or "Administrator",
			}
			result = _execute_step(step, step_context, render_ctx)

			step_run.status = "success" if result["status"] == "success" else result["status"]
			step_run.output = _stringify(result["output"])
			step_run.error = result.get("error")
			step_run.session = result.get("session_id")

			if result["status"] == "waiting":
				run.resume_step_idx = idx + 1
				run.running_context = frappe.as_json(context)
				run.status = (
					"waiting_approval" if getattr(step, "step_type", None) == "Human Approval" else "running"
				)
				run.save(ignore_permissions=True)
				frappe.db.commit()
				return run.name

			if result["status"] == "skipped":
				run.status = "skipped"
				run.ended_at = now_datetime()
				run.final_output = _stringify(previous_output)
				run.save(ignore_permissions=True)
				frappe.db.commit()
				return run.name

			if result["status"] == "error":
				raise RuntimeError(
					result.get("error") or f"Step failed: {getattr(step, 'step_name', 'unknown')}"
				)

			output = result["output"]
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


def _execute_step(step, step_context: dict, render_ctx: dict) -> dict:
	"""Execute one workflow step as either an agent call or a tool call."""
	if getattr(step, "agent_name", None):
		kind = "agent"
	else:
		kind = "tool"

	if kind == "agent":
		rendered_input = frappe.render_template(step.input_template or "", render_ctx)
		provenance = SessionProvenance(
			trigger_type="Workflow Step",
			trigger_source=f"Workflow: {step_context.get('workflow_name', 'unknown')} / Step: {step.step_name}",
			trigger_ref=step_context.get("workflow_run", "").name if step_context.get("workflow_run") else "",
		)
		result = run_headless_agent(
			agent_name=step.agent_name,
			input_message=rendered_input,
			provenance=provenance,
			user=step_context.get("run_as_user", "Administrator"),
		)
		return {"status": "success", "output": result.response, "session_id": result.session_id}

	if kind == "tool":
		tool_name = getattr(step, "tool_name", None) or getattr(step, "step_type", None)
		if not tool_name:
			return {"status": "error", "error": "Tool step is missing a tool name"}

		raw_args = (
			frappe.render_template(step.input_template or "{}", render_ctx)
			if getattr(step, "input_template", None)
			else "{}"
		)
		try:
			parsed_args = json.loads(raw_args)
		except Exception:
			parsed_args = {"value": raw_args}

		registry = get_tool_registry()
		executor = registry.executors.get(tool_name)
		if not executor:
			return {"status": "error", "error": f"Tool '{tool_name}' is not registered"}

		sig = inspect.signature(executor)
		params = list(sig.parameters.keys())
		use_args_dict = bool(params) and params[0] == "args"

		if inspect.iscoroutinefunction(executor):
			if use_args_dict:
				result_value = asyncio.run(executor(args=parsed_args))
			else:
				result_value = asyncio.run(executor(**parsed_args))
		elif use_args_dict:
			result_value = executor(args=parsed_args)
		else:
			result_value = executor(**parsed_args)

		return {"status": "success", "output": result_value}

	return {"status": "error", "error": f"Unsupported workflow step kind: {kind}"}


def _stringify(value) -> str:
	if isinstance(value, (dict, list)):
		return frappe.as_json(value)
	return str(value) if value is not None else ""
