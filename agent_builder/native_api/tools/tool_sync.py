# agent_builder/native_api/tools/tool_sync.py
"""Keeps the `Tool Group` / `Agent Tool` doctypes in step with whatever
load_tools() actually found on disk.

This is the DB-backed control surface the Agent Builder "Tools" section
reads and writes. The registry (decorator.ToolRegistry) stays the runtime
source of truth for *what a tool does*; these doctypes are purely the
on/off switches layered on top, plus grouping/description metadata for
the UI.

Sync semantics, deliberately conservative:
  - New tool/group on disk, no DB row yet -> create it, is_enabled=1.
  - Tool/group already has a DB row -> NEVER touch is_enabled. An admin's
    choice to disable something must survive every reload/deploy.
  - description is always refreshed from the schema (it's not something
    an admin hand-edits; schema.py is the source of truth for it).
  - DB row exists but nothing on disk matches it anymore -> mark
    is_orphaned=1, leave is_enabled alone, never delete. Cleanup is a
    deliberate admin action (see delete_orphaned_tools/groups below), not
    something a reload should ever do silently.
  - A tool/group that reappears after being orphaned has is_orphaned
    cleared automatically.
"""

import logging

import frappe

from agent_builder.native_api.tools.decorator import ToolRegistry

logger = logging.getLogger(__name__)


def sync_tool_registry(registry: ToolRegistry, tool_to_group: dict[str, str]) -> None:
	"""tool_to_group: {tool_name: tool_group_dir_name}, as built by loader.py
	while it was walking the tools/ directory."""
	if not frappe.db:
		# No DB context (e.g. import-time call outside a Frappe request/job) —
		# nothing to sync against; skip quietly.
		return

	now = frappe.utils.now_datetime()
	schemas_by_name = {
		(s.get("function", {}).get("name") or s.get("name")): s for s in registry.get_tool_schemas()
	}

	# ---- Tool Group -----------------------------------------------------
	seen_groups = set(tool_to_group.values())
	existing_groups = set(frappe.get_all("Tool Group", pluck="name"))

	for group_name in seen_groups:
		if group_name in existing_groups:
			frappe.db.set_value(
				"Tool Group", group_name, {"is_orphaned": 0, "last_synced": now}, update_modified=False
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Tool Group",
					"group_name": group_name,
					"is_enabled": 1,
					"last_synced": now,
				}
			).insert(ignore_permissions=True)

	for stale_group in existing_groups - seen_groups:
		frappe.db.set_value("Tool Group", stale_group, "is_orphaned", 1, update_modified=False)

	# ---- Agent Tool -------------------------------------------------------
	existing_tools = set(frappe.get_all("Agent Tool", pluck="name"))

	for tool_name, group_name in tool_to_group.items():
		description = _extract_description(schemas_by_name.get(tool_name))
		if tool_name in existing_tools:
			frappe.db.set_value(
				"Agent Tool",
				tool_name,
				{
					"tool_group": group_name,
					"description": description,
					"is_orphaned": 0,
					"last_synced": now,
				},
				update_modified=False,
			)
		else:
			frappe.get_doc(
				{
					"doctype": "Agent Tool",
					"tool_name": tool_name,
					"tool_group": group_name,
					"description": description,
					"is_enabled": 1,
					"last_synced": now,
				}
			).insert(ignore_permissions=True)

	for stale_tool in existing_tools - set(tool_to_group.keys()):
		frappe.db.set_value("Agent Tool", stale_tool, "is_orphaned", 1, update_modified=False)

	frappe.db.commit()
	logger.info(
		f"Tool sync: {len(seen_groups)} groups, {len(tool_to_group)} tools "
		f"({len(existing_groups - seen_groups)} orphaned groups, "
		f"{len(existing_tools - set(tool_to_group.keys()))} orphaned tools)"
	)


def _extract_description(schema: dict | None) -> str:
	if not schema:
		return ""
	return schema.get("function", {}).get("description") or schema.get("description") or ""


# =========================================================================
# Filtering — the actual enforcement point, consumed by setup.py
# =========================================================================


def get_globally_disabled_tool_names() -> set[str]:
	"""Tool names to drop from every agent's schema list, regardless of
	that agent's own tool_mode/allowed_tools: tools explicitly disabled,
	or tools whose group is disabled."""
	disabled_groups = set(
		frappe.get_all("Tool Group", filters={"is_enabled": 0}, pluck="name")
	)
	disabled_direct = set(
		frappe.get_all("Agent Tool", filters={"is_enabled": 0}, pluck="name")
	)
	if disabled_groups:
		disabled_via_group = set(
			frappe.get_all(
				"Agent Tool", filters={"tool_group": ["in", list(disabled_groups)]}, pluck="name"
			)
		)
	else:
		disabled_via_group = set()
	return disabled_direct | disabled_via_group


# =========================================================================
# Admin-triggered actions
# =========================================================================


@frappe.whitelist()
def resync_tools() -> dict:
	"""Manual 'Sync Tools' button — forces a fresh registry build (which
	runs sync_tool_registry as a side effect) without requiring a worker
	restart. Useful right after adding/removing a tool file."""
	frappe.only_for("System Manager")
	from agent_builder.native_api.agent.setup import get_tool_registry, invalidate_prompt_cache

	invalidate_prompt_cache()
	registry = get_tool_registry(force_reload=True)
	return {
		"tool_count": len(registry.get_tool_schemas()),
		"group_count": frappe.db.count("Tool Group"),
	}


@frappe.whitelist()
def delete_orphaned(doctype: str) -> dict:
	"""Deliberate cleanup: permanently remove every row currently flagged
	is_orphaned=1 for the given doctype ('Tool Group' or 'Agent Tool').
	Never called automatically."""
	frappe.only_for("System Manager")
	if doctype not in ("Tool Group", "Agent Tool"):
		frappe.throw("doctype must be 'Tool Group' or 'Agent Tool'")

	names = frappe.get_all(doctype, filters={"is_orphaned": 1}, pluck="name")
	for name in names:
		frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
	frappe.db.commit()
	return {"deleted": names}