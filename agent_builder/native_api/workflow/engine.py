# agent_builder/native_api/workflow/engine.py
"""Minimal workflow engine.

A workflow is a chain of steps stored as JSON on an `Agent Workflow` doc.
There are exactly 3 step primitives:

  - tool:   dispatch a registered tool (this includes delegate_task —
            delegate_task is NOT a special step type, it's just a tool
            that happens to invoke a Skill marked is_agent=1)
  - branch: deterministic jump based on the previous step's output
  - loop:   deterministic repeat of a sub-sequence of step ids, based on
            the previous step's output

Data flow is deliberately simple: each step sees only `output`, the raw
result of the immediately preceding step (no accumulated context object).
Steps reference it via "{{output.field.path}}" in string args; the same
mechanism serves both "auto-pass whole output" (don't reference it, or
reference "{{output}}" directly) and "explicit field mapping"
("{{output.rows[0].id}}"-style dotted access).

This engine intentionally shares NO infrastructure with the older
Workflow/workflow_engine.py (Agent/HTTP/Condition/Transform/Frappe
Action/Delay/Human Approval node system) — separate DocType, separate
module, separate execution path.
"""

import asyncio
import json
import re

import frappe
from simpleeval import EvalWithCompoundTypes

from agent_builder.native_api.agent.setup import get_tool_registry
from agent_builder.native_api.tools.executor import ToolExecutor

REF = re.compile(r"\{\{output\.([\w.]+)\}\}")


def resolve_refs(value, output):
	"""Recursively substitute {{output.x.y}} references in strings/dicts/lists."""
	if isinstance(value, str):
		return REF.sub(lambda m: str(_dig(output, m.group(1))), value)
	if isinstance(value, dict):
		return {k: resolve_refs(v, output) for k, v in value.items()}
	if isinstance(value, list):
		return [resolve_refs(v, output) for v in value]
	return value


def _dig(obj, path: str):
	for part in path.split("."):
		if isinstance(obj, dict):
			obj = obj[part]
		elif isinstance(obj, list):
			obj = obj[int(part)]
		else:
			obj = getattr(obj, part)
	return obj


def _eval(expr: str, output) -> bool:
	"""Restricted expression evaluation for branch/loop conditions.

	Uses simpleeval rather than a stripped-builtins eval() — nulling
	__builtins__ does NOT close off every code-execution gadget chain
	(e.g. via __class__.__base__.__subclasses__()), whereas simpleeval
	implements its own restricted grammar with no path to arbitrary code
	execution at all. Matters because condition strings could plausibly
	be authored by an LLM (via a future create_workflow-style tool), not
	just typed by hand.
	"""
	evaluator = EvalWithCompoundTypes(names={"output": output})
	return bool(evaluator.eval(expr))


async def _execute_step(step: dict, output, executor: ToolExecutor):
	if step["type"] != "tool":
		raise ValueError(f"'{step['type']}' is a control-flow step, not directly executable")

	args = resolve_refs(step.get("args", {}), output)
	raw = await executor._dispatch(step["tool"], json.dumps(args))
	try:
		return json.loads(raw)
	except (json.JSONDecodeError, TypeError):
		# Tool didn't return JSON (unexpected, but don't crash the workflow
		# over it) — pass the raw string through as the next step's output.
		return raw


async def _run_workflow_async(workflow_name: str, initial_input: dict | None = None) -> dict:
	wf = frappe.get_doc("Agent Workflow", workflow_name)
	if not wf.get("is_enabled", True):
		raise frappe.ValidationError(f"Workflow '{workflow_name}' is disabled")

	steps_list = frappe.parse_json(wf.steps)
	steps = {s["id"]: s for s in steps_list}
	order = [s["id"] for s in steps_list]

	executor = ToolExecutor(get_tool_registry())
	output = initial_input or {}
	log = []

	idx = 0
	while idx < len(order):
		step = steps[order[idx]]

		if step["type"] == "branch":
			target = step["if_true"] if _eval(step["condition"], output) else step["if_false"]
			log.append({"step": step["id"], "type": "branch", "took": target})
			idx = order.index(target)
			continue

		if step["type"] == "loop":
			iterations = 0
			max_iter = step.get("max_iterations", 10)
			while _eval(step["condition"], output) and iterations < max_iter:
				for body_id in step["body"]:
					output = await _execute_step(steps[body_id], output, executor)
					log.append({"step": body_id, "type": steps[body_id]["type"], "output": output})
				iterations += 1
			log.append({"step": step["id"], "type": "loop", "iterations": iterations})
			idx += 1
			continue

		output = await _execute_step(step, output, executor)
		log.append({"step": step["id"], "type": step["type"], "tool": step.get("tool"), "output": output})
		idx += 1

	return {"final_output": output, "log": log}


def run_workflow(workflow_name: str, initial_input: dict | None = None) -> dict:
	"""Synchronous entry point — mirrors runner.py's asyncio.run(...) wrapping
	pattern for consistency across the codebase.

	No session/depth seeding needed here: delegate_task now derives depth
	by looking up its parent Agent Session's own delegate_depth in the DB
	(defaulting to 0 when there's no parent, which is exactly the
	top-level-workflow case), rather than reading any in-memory context.
	"""
	return asyncio.run(_run_workflow_async(workflow_name, initial_input))