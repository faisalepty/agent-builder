# agent_builder/native_api/agent_management.py
"""Whitelisted read endpoints for the Agent Management Desk page.

Deliberately separate from verify.py — verify.py is the chat runtime
surface (send message, stream, stop); this module is the ops/observability
surface (browse sessions + lineage, browse workflow definitions). Keeping
them apart means neither has to reason about the other's concerns.
"""
import frappe


@frappe.whitelist()
def get_sessions(limit=100):
	"""Return top-level Agent Sessions (parent_session is empty) with each
	one's delegate children nested inline, so the frontend can render a
	call-stack tree without doing N+1 lookups per row.

	Only System Manager can browse other users' sessions; a non-admin only
	sees their own — mirrors the permission shape of get_chats() in
	verify.py, just widened to include ended/errored sessions and lineage.
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

	# Recursively attach — depth is capped low (MAX_DELEGATE_DEPTH = 2) so
	# this recursion is bounded and cheap, not a real risk of blowing the
	# stack or fan-out on pathological data.
	def attach(session):
		session["children"] = [attach(c) for c in children_by_parent.get(session["name"], [])]
		return session

	return [attach(s) for s in top_level]


@frappe.whitelist()
def get_workflows():
	"""List Agent Workflow definitions — metadata only, no step contents.
	The (future) canvas page is where steps get viewed/edited; this list
	is a launcher into that, not an editor.
	"""
	workflows = frappe.get_all(
		"Agent Workflow",
		fields=["name", "workflow_name", "description", "is_enabled", "modified"],
		order_by="modified desc",
	)
	# step_count is derived, not stored — cheap enough at list-page scale
	for wf in workflows:
		steps_json = frappe.db.get_value("Agent Workflow", wf.name, "steps")
		try:
			wf["step_count"] = len(frappe.parse_json(steps_json) or [])
		except Exception:
			wf["step_count"] = 0
	return workflows