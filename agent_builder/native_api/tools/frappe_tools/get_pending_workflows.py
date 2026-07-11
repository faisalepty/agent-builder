# tools/frappe_tools/document_pending_approvals.py

import json
import frappe
from frappe.query_builder import DocType
from frappe.model.workflow import get_transitions
from agent_builder.native_api.tools.decorator import tool

MAX_TRANSITION_DOCS = 20


@tool(schema_name="frappe_get_pending_approvals")
def frappe_get_pending_approvals(args: dict, **kwargs) -> str:
    """Get documents pending the current user's approval, via the Workflow Action system."""
    doctype_filter = args.get("doctype")
    limit = min(args.get("limit", 50), 200)
    include_actions = args.get("include_actions", True)

    user = frappe.session.user
    roles = frappe.get_roles(user)

    try:
        WA = DocType("Workflow Action")
        WAPR = DocType("Workflow Action Permitted Role")

        role_subquery = (
            frappe.qb.from_(WA)
            .join(WAPR).on(WA.name == WAPR.parent)
            .select(WA.name)
            .where(WAPR.role.isin(roles))
        )

        query = (
            frappe.qb.from_(WA)
            .select(WA.name, WA.reference_doctype, WA.reference_name, WA.workflow_state, WA.user, WA.creation)
            .where(WA.status == "Open")
            .orderby(WA.creation, order=frappe.qb.desc)
            .limit(limit)
        )

        if user != "Administrator":
            query = query.where(WA.name.isin(role_subquery) | (WA.user == user))
        if doctype_filter:
            query = query.where(WA.reference_doctype == doctype_filter)

        pending = query.run(as_dict=True)

        if not pending:
            return json.dumps({
                "total_pending": 0,
                "doctypes_with_pending": [],
                "pending_approvals": {},
            })

        action_names = [a.name for a in pending]
        roles_rows = frappe.get_all(
            "Workflow Action Permitted Role",
            filters={"parent": ["in", action_names]},
            fields=["parent", "role"],
        )
        roles_map = {}
        for r in roles_rows:
            roles_map.setdefault(r.parent, []).append(r.role)

        transitions_map = {}
        if include_actions:
            seen = set()
            for action in pending:
                key = (action.reference_doctype, action.reference_name)
                if key in seen or len(seen) >= MAX_TRANSITION_DOCS:
                    continue
                seen.add(key)
                try:
                    doc = frappe.get_doc(action.reference_doctype, action.reference_name)
                    transitions_map[key] = [
                        {"action": t.get("action"), "next_state": t.get("next_state")}
                        for t in get_transitions(doc)
                    ]
                except Exception:
                    transitions_map[key] = []

        grouped = {}
        for action in pending:
            dt = action.reference_doctype
            key = (dt, action.reference_name)
            entry = {
                "document_name": action.reference_name,
                "workflow_state": action.workflow_state,
                "permitted_roles": roles_map.get(action.name, []),
                "creation": str(action.creation),
            }
            if include_actions and key in transitions_map:
                entry["available_actions"] = transitions_map[key]
            grouped.setdefault(dt, []).append(entry)

        result = {
            "total_pending": len(pending),
            "doctypes_with_pending": list(grouped.keys()),
            "pending_approvals": grouped,
        }

        unique_docs = {(a.reference_doctype, a.reference_name) for a in pending}
        if include_actions and len(unique_docs) > MAX_TRANSITION_DOCS:
            result["actions_truncated"] = True
            result["actions_truncated_note"] = (
                f"Available actions shown for the first {MAX_TRANSITION_DOCS} documents only. "
                "Filter by doctype or set include_actions=false for the full list."
            )

        return json.dumps(result)

    except Exception as e:
        frappe.log_error(title="Pending Approvals Error", message=str(e))
        return json.dumps({"error": str(e)})