# agent_builder/native_api/workflow/engine.py
"""Workflow engine.

Step types: tool, branch, loop, note, trigger, workflow.

There is no dedicated "human_approval" step type — approval is just a
regular Tool step calling the `human_approval` tool
(tools/workflow_tools/human_approval.py). That tool returns a
{"__workflow_pause__": True, ...} marker; _execute_tool_step below turns
that into a WorkflowPaused exception, which the main loop catches to
persist the run as Paused and hand control back to the caller — the same
pause/resume mechanics as before, just triggered by tool output instead
of a step-type branch. This keeps human_approval visible and usable
anywhere a normal tool is (get_available_tools, an agent's own tool list,
etc.) rather than being a workflow-only special case.

Every run is persisted as an "Agent Workflow Run" document from the
moment it starts, enabling execution history, resume-after-pause, and an
error_workflow payload on failure.
"""

import asyncio
import json
import re

import frappe
from simpleeval import EvalWithCompoundTypes

from agent_builder.native_api.agent.setup import get_tool_registry
from agent_builder.native_api.tools.executor import ToolExecutor

REF = re.compile(r"\{\{output(\.([\w.]+))?\}\}")

# Sub-workflow ("workflow" step type) recursion guard. run_workflow is a
# fresh asyncio.run() per call rather than one continuous task tree, so
# depth is threaded explicitly through every recursive _run_workflow_async
# call instead of relying on a contextvars.ContextVar the way Agent.run's
# delegate_task does.
MAX_WORKFLOW_DEPTH = 3


class WorkflowPaused(Exception):
    """Raised when a tool's result carries the __workflow_pause__ marker
    (currently only the human_approval tool does this). Caught by the
    main loop in _run_workflow_async — never lets step-level retry or
    continue_on_fail swallow it, since pausing isn't a failure.
    """

    def __init__(self, info: dict):
        self.info = info
        super().__init__(info.get("message", "Workflow paused"))


def _maybe_parse_json(value):
    """If value is a string containing valid JSON, parse and return it as
    a Python dict/list. Otherwise, return the original value unchanged.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
    return value


def resolve_refs(value, output):
    """Resolve {{output}} and {{output.path}} references against the current
    workflow output.

    Supports three patterns:
    1. Standalone {{output}} or {{output.path}}:
       Returns the native Python object (dict, list, etc.) directly.
       If the resolved value is a JSON string, it is parsed into a dict.
    2. JSON template with embedded refs:
       e.g. '{"customer": "{{output.name}}"}' -> replaces refs, parses
       the resulting string back into a dict.
    3. Plain text template:
       e.g. 'Summarize this: {{output.text}}' -> returns the string.
    """
    if isinstance(value, str):
        val_strip = value.strip()
        
        # 1. Standalone {{ output }} or {{ output.path }}
        m = REF.fullmatch(val_strip)
        if m:
            path = m.group(2)
            if not path:
                return _maybe_parse_json(output)
            return _maybe_parse_json(_dig(output, path))

        # 2. Embedded refs in a larger template (JSON or text)
        def repl(m):
            path = m.group(2)
            if not path:
                return json.dumps(output, default=str)
            
            val = _dig(output, path)
            if isinstance(val, str):
                return val  # Let surrounding template quotes handle stringification
            return json.dumps(val, default=str)

        resolved = REF.sub(repl, val_strip)

        # 3. If the resolved string looks like JSON, parse it back to an object.
        return _maybe_parse_json(resolved)

    if isinstance(value, dict):
        return {k: resolve_refs(v, output) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(v, output) for v in value]
    return value


def _dig(obj, path: str):
    """Traverse a dotted path against a dictionary/list. If an intermediate
    value is a JSON string, parse it automatically so paths like 
    `output.response.doc` work when `response` returns a JSON string.
    """
    for part in path.split("."):
        # Automatically parse JSON strings encountered during traversal
        if isinstance(obj, str):
            obj = _maybe_parse_json(obj)
            if obj is None:
                return None

        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


def _eval(expr: str, output) -> bool:
    evaluator = EvalWithCompoundTypes(names={"output": output})
    return bool(evaluator.eval(expr))


async def _execute_tool_step(step: dict, output, executor: ToolExecutor):
    args = resolve_refs(step.get("args", {}), output)
    raw = await executor._dispatch(step["tool"], json.dumps(args))
    parsed = json.loads(raw)

    if isinstance(parsed, dict) and parsed.get("__workflow_pause__"):
        raise WorkflowPaused(parsed)

    if isinstance(parsed, dict) and parsed.get("error") and not step.get("continue_on_fail", False):
        raise Exception(f"Tool '{step['tool']}' returned error: {parsed.get('error')}")
    return parsed


async def _execute_subworkflow_step(step: dict, output, depth: int):
    """Execute another Agent Workflow as a step — same depth-guard shape
    as delegate_task's MAX_DELEGATE_DEPTH, just threaded as a plain
    argument since run_workflow has no single running event loop to hang
    a ContextVar off of across calls.
    """
    if depth >= MAX_WORKFLOW_DEPTH:
        return {
            "error": f"Max sub-workflow depth ({MAX_WORKFLOW_DEPTH}) reached; "
            "cannot call a workflow from within a workflow step at this depth.",
            "error_type": "max_depth_exceeded",
        }

    sub_workflow_name = step.get("workflow_name")
    if not sub_workflow_name:
        raise ValueError(f"Step '{step['id']}' is type 'workflow' but has no workflow_name")

    input_mapping = step.get("input_mapping", {})
    sub_input = resolve_refs(input_mapping, output) if input_mapping else output

    result = await _run_workflow_async(sub_workflow_name, sub_input, depth=depth + 1)
    return result.get("final_output")


async def _execute_step(step: dict, output, executor: ToolExecutor, depth: int = 0):
    """Execute a single 'tool' or 'workflow' step, with optional
    step-level wait/retry layered on top of executor.py's own
    tool-dispatch retry.
    """
    if step["type"] not in ("tool", "workflow"):
        raise ValueError(f"'{step['type']}' is a control-flow step, not directly executable via _execute_step")

    wait_seconds = step.get("wait_seconds", 0)
    if wait_seconds:
        await asyncio.sleep(wait_seconds)

    max_retries = int(step.get("max_retries", 0)) if step.get("retry_on_fail") else 0
    wait_between_ms = int(step.get("wait_between_ms", 1000))

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            if step["type"] == "workflow":
                return await _execute_subworkflow_step(step, output, depth)
            return await _execute_tool_step(step, output, executor)
        except WorkflowPaused:
            raise
        except Exception as e:
            last_exc = e
            if step.get("continue_on_fail", False):
                return {"error": str(e), "failed_step": step["id"]}
            if attempt < max_retries:
                await asyncio.sleep(wait_between_ms / 1000)
                continue
            raise

    raise last_exc  # pragma: no cover — loop above always returns or raises


async def _run_workflow_async(
    workflow_name: str,
    initial_input: dict | None = None,
    depth: int = 0,
    resume_run: str | None = None,
) -> dict:
    """Run a workflow, persisting it as an Agent Workflow Run throughout."""
    wf = frappe.get_doc("Agent Workflow", workflow_name)
    if not wf.get("is_enabled", True):
        raise frappe.ValidationError(f"Workflow '{workflow_name}' is disabled")

    steps_list = frappe.parse_json(wf.steps or "[]")
    if not steps_list:
        raise frappe.ValidationError(f"Workflow '{workflow_name}' has no steps.")

    steps = {s["id"]: s for s in steps_list}
    order = [s["id"] for s in steps_list]

    executor = ToolExecutor(get_tool_registry())

    if resume_run:
        run_doc = frappe.get_doc("Agent Workflow Run", resume_run)
        state = frappe.parse_json(run_doc.resume_state or "{}")
        output = state.get("output", initial_input or {})
        log = frappe.parse_json(run_doc.log or "[]")
        idx = state.get("idx", 0)
    else:
        run_doc = frappe.get_doc(
            {
                "doctype": "Agent Workflow Run",
                "workflow": workflow_name,
                "status": "Running",
                "started_at": frappe.utils.now_datetime(),
                "log": "[]",
            }
        )
        run_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        output = initial_input or {}
        log = []
        idx = 0

    try:
        while idx < len(order):
            step = steps[order[idx]]

            if step["type"] in ("note", "trigger"):
                idx += 1
                continue

            if step["type"] == "branch":
                target = step["if_true"] if _eval(step["condition"], output) else step["if_false"]
                if not target:
                    raise ValueError(f"Branch '{step['id']}' has no target for the evaluated condition.")
                log.append({"step": step["id"], "type": "branch", "took": target})
                idx = order.index(target)
                continue

            if step["type"] == "loop":
                iterations = 0
                max_iter = step.get("max_iterations", 10)
                while _eval(step["condition"], output) and iterations < max_iter:
                    for body_id in step["body"]:
                        output = await _execute_step(steps[body_id], output, executor, depth=depth)
                        log.append(
                            {
                                "step": body_id,
                                "type": steps[body_id]["type"],
                                "tool": steps[body_id].get("tool"),
                                "output": output,
                            }
                        )
                    iterations += 1
                log.append({"step": step["id"], "type": "loop", "iterations": iterations})
                idx += 1
                continue

            try:
                output = await _execute_step(step, output, executor, depth=depth)
            except WorkflowPaused as p:
                run_doc.status = "Paused"
                run_doc.paused_step = step["id"]
                run_doc.log = frappe.as_json(log)
                run_doc.resume_state = frappe.as_json({"idx": idx + 1, "output": output})
                run_doc.save(ignore_permissions=True)
                frappe.db.commit()
                return {
                    "final_output": output,
                    "log": log,
                    "status": "Paused",
                    "run_name": run_doc.name,
                    "paused_step": step["id"],
                    "message": p.info.get("message"),
                    "channel": p.info.get("channel"),
                }

            log.append({"step": step["id"], "type": step["type"], "tool": step.get("tool"), "output": output})
            idx += 1

        run_doc.status = "Success"
        run_doc.finished_at = frappe.utils.now_datetime()
        run_doc.log = frappe.as_json(log)
        run_doc.final_output = frappe.as_json(output)
        run_doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {"final_output": output, "log": log, "status": "Success", "run_name": run_doc.name}

    except Exception as e:
        run_doc.status = "Failed"
        run_doc.finished_at = frappe.utils.now_datetime()
        run_doc.log = frappe.as_json(log)
        run_doc.error = str(e)
        run_doc.save(ignore_permissions=True)
        frappe.db.commit()

        error_workflow = wf.get("error_workflow")
        if error_workflow and error_workflow != workflow_name:
            try:
                frappe.enqueue(
                    method="agent_builder.native_api.workflow.engine.run_workflow",
                    queue="short",
                    timeout=300,
                    workflow_name=error_workflow,
                    initial_input={
                        "failed_workflow": workflow_name,
                        "failed_run": run_doc.name,
                        "error": str(e),
                        "log": log,
                    },
                )
            except Exception:
                frappe.log_error(title="Error Workflow Dispatch Failed", message=frappe.get_traceback())

        raise


def run_workflow(workflow_name: str, initial_input: dict | None = None, depth: int = 0) -> dict:
    return asyncio.run(_run_workflow_async(workflow_name, initial_input, depth=depth))


def resume_workflow(run_name: str, decision: str, edited_output: dict | None = None) -> dict:
    """Resume a run paused by a human_approval tool call."""
    run_doc = frappe.get_doc("Agent Workflow Run", run_name)
    if run_doc.status != "Paused":
        raise frappe.ValidationError(f"Run '{run_name}' is not paused (status: {run_doc.status})")

    if decision == "reject":
        run_doc.status = "Failed"
        run_doc.finished_at = frappe.utils.now_datetime()
        run_doc.error = "Rejected at human approval step"
        run_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "Failed", "run_name": run_name}

    if edited_output is not None:
        state = frappe.parse_json(run_doc.resume_state or "{}")
        state["output"] = edited_output
        run_doc.resume_state = frappe.as_json(state)
        run_doc.save(ignore_permissions=True)
        frappe.db.commit()

    return asyncio.run(_run_workflow_async(run_doc.workflow, resume_run=run_name))