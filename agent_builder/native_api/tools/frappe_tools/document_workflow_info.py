# tools/frappe_tools/document_workflow_info.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool

@tool(schema_name="frappe_get_workflow_info")
def frappe_get_workflow_info(args: dict, **kwargs) -> str:
    """Get workflow states and transitions for a DocType, if one is defined."""
    doctype = args.get("doctype")

    if not doctype:
        return json.dumps({"error": "doctype is required"})

    try:
        if not frappe.db.exists("DocType", doctype):
            return json.dumps({"error": f"DocType '{doctype}' not found"})

        workflow_name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1}, "name")

        if not workflow_name:
            return json.dumps({
                "doctype": doctype,
                "has_workflow": False,
                "message": f"No active workflow defined for '{doctype}'. Use frappe_submit_doc/frappe_save_doc directly.",
            })

        workflow_doc = frappe.get_doc("Workflow", workflow_name)

        states = [
            {
                "state": s.state,
                "doc_status": s.doc_status,
                "allow_edit": s.allow_edit,
            }
            for s in workflow_doc.states
        ]

        transitions = [
            {
                "state": t.state,
                "action": t.action,
                "next_state": t.next_state,
                "allowed": t.allowed,
            }
            for t in workflow_doc.transitions
        ]

        return json.dumps({
            "doctype": doctype,
            "has_workflow": True,
            "workflow_name": workflow_doc.name,
            "workflow_state_field": workflow_doc.workflow_state_field,
            "states": states,
            "transitions": transitions,
        })

    except Exception as e:
        frappe.log_error(title="Get Workflow Info Error", message=f"Error getting workflow for {doctype}: {str(e)}")
        return json.dumps({"error": str(e), "doctype": doctype})