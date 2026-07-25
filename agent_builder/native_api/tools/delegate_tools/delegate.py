# agent_builder/native_api/tools/agent_tools/delegate_task.py
import json

import frappe

from agent_builder.native_api.agent.agent import current_session_id
from agent_builder.native_api.agent.runner import SessionProvenance, run_headless_agent
from agent_builder.native_api.tools.decorator import tool

MAX_DELEGATE_DEPTH = 2


@tool(schema_name="delegate_task")
def delegate_task(args: dict, **kwargs) -> str:
	"""Delegate a self-contained sub-task to a named agent (a Skill with
	is_agent=1), running it as a fresh, isolated agent loop. Only the final
	answer crosses back to the caller.

	Rules this tool upholds:
	  - The sub-run gets its OWN Conversation/session_id — this tool never
	    reuses the caller's session_id, which is what keeps the sub-run's
	    tool_start/tool_result/token events off the parent's realtime
	    channel (no cross-tab bleed, no UI noise in chat).
	  - Always uses the non-streaming runner path (run_headless_agent).
	    Delegates are headless; nothing about their intermediate turns
	    reaches on_token/on_reasoning callbacks.
	  - Depth-limited via frappe.local.delegate_depth, which Agent.run()
	    seeds to 0 and this tool increments for the duration of the
	    sub-run, then restores. This works identically whether the caller
	    is the interactive agent loop or the workflow engine, since both
	    set frappe.local.current_session_id / delegate_depth the same way.
	  - This tool is itself just a registered tool like any other — it is
	    NOT a special step type in the workflow engine. A workflow step
	    that calls "delegate_task" is dispatched through the exact same
	    ToolExecutor._dispatch path as frappe_get_list, create_skill, etc.
	  - Cost/telemetry still roll up as a real Agent Session row
	    (trigger_type="Delegate", trigger_source=parent session id,
	    parent_session/delegated_skill/delegate_depth stamped after the
	    run), so cost rollup and eval infra pick it up; it's just not
	    rendered inline in the parent's chat.
	"""
	agent_skill_name = args.get("agent_name")
	task = args.get("task")
	if not agent_skill_name:
		return json.dumps({"error": "agent_name (a Skill with is_agent=1) is required"})
	if not task:
		return json.dumps({"error": "task is required"})

	if not frappe.db.exists("Skill", agent_skill_name):
		return json.dumps({"error": f"Skill '{agent_skill_name}' does not exist"})

	skill = frappe.get_doc("Skill", agent_skill_name)
	if not skill.get("is_agent"):
		return json.dumps(
			{
				"error": f"Skill '{agent_skill_name}' is not marked is_agent — it can't be delegated to.",
				"error_type": "not_an_agent",
			}
		)
	if not skill.get("is_enabled", True):
		return json.dumps({"error": f"Skill '{agent_skill_name}' is disabled", "error_type": "disabled"})

	# The caller's session id comes from the ContextVar set once at the top
	# of Agent.run() — safe under asyncio.gather's parallel tool calls,
	# and doesn't depend on OS thread/greenlet identity the way
	# frappe.local does (that dependency is what broke chat under RQ).
	parent_session_id = current_session_id.get()

	# Depth is read from the PARENT session's own stamped delegate_depth —
	# not from any in-memory context — because a delegate's sub-run starts
	# a brand new asyncio.run() call stack in runner.py, which is outside
	# this ContextVar's scope. Looking it up from the persisted Agent
	# Session row is slightly more DB I/O but is correct regardless of
	# which event loop / worker / task the call happens on.
	depth = 0
	if parent_session_id and frappe.db.exists("Agent session", parent_session_id):
		depth = frappe.db.get_value("Agent session", parent_session_id, "delegate_depth") or 0

	if depth >= MAX_DELEGATE_DEPTH:
		return json.dumps(
			{
				"error": f"Max delegation depth ({MAX_DELEGATE_DEPTH}) reached; "
				"cannot delegate further from within a delegate.",
				"error_type": "max_depth_exceeded",
			}
		)

	provenance = SessionProvenance(
		trigger_type="Delegate",
		trigger_source=parent_session_id or "unknown-parent",
		trigger_ref=f"depth-{depth + 1}",
	)

	try:
		result = run_headless_agent(
			agent_name=None,  # not an Agent Definition — instructions come from the skill instead
			input_message=task,
			provenance=provenance,
			user=frappe.session.user,
			skill_injection=skill.content,
		)
	except Exception as e:
		frappe.log_error(title="Delegate Task Error", message=f"agent={agent_skill_name!r} task={task!r}: {e!s}")
		return json.dumps({"error": str(e)})

	# Stamp lineage fields the runner doesn't know about — parent_session,
	# delegated_skill, delegate_depth aren't part of SessionProvenance since
	# they're delegate-specific, not general trigger metadata.
	frappe.db.set_value(
		"Agent session",
		result.session_id,
		{
			"parent_session": parent_session_id or None,
			"delegated_skill": agent_skill_name,
			"delegate_depth": depth + 1,
		},
		update_modified=False,
	)

	return json.dumps(
		{
			"response": result.response,
			"ended_reason": result.ended_reason,
			"sub_session_id": result.session_id,
		},
		default=str,
	)