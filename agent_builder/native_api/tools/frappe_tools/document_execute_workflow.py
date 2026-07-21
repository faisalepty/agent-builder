# tools/frappe_tools/document_run_workflow.py

import json

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from agent_builder.native_api.tools.decorator import tool


def _list_transitions(doc) -> list:
	try:
		transitions = get_transitions(doc)
	except Exception:
		return []
	return [
		{
			"action": t.get("action"),
			"next_state": t.get("next_state"),
			"allowed_roles": t.get("allowed", "").split(",") if t.get("allowed") else [],
		}
		for t in transitions
	]


@tool(schema_name="frappe_run_workflow")
def frappe_run_workflow(args: dict, **kwargs) -> str:
	"""Execute a workflow action (Approve, Reject, Submit for Review, etc.) on a document."""
	doctype = args.get("doctype")
	name = args.get("name")
	action = args.get("action")

	if not doctype or not name or not action:
		return json.dumps({"error": "doctype, name, and action are all required"})

	try:
		if not frappe.db.exists(doctype, name):
			return json.dumps({"error": f"{doctype} '{name}' not found"})

		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")

		original_state = getattr(doc, "workflow_state", None)

		workflow_name = get_workflow_name(doctype)
		if not workflow_name:
			return json.dumps(
				{
					"error": f"No workflow configured for {doctype}. Use frappe_save_doc or frappe_submit_doc instead.",
				}
			)

		available = _list_transitions(doc)
		available_actions = [t["action"] for t in available]

		if action not in available_actions:
			return json.dumps(
				{
					"error": f"Action '{action}' is not available for document in state '{original_state}'",
					"current_state": original_state,
					"available_actions": available_actions,
				}
			)

		before_docstatus = doc.docstatus
		updated_doc = apply_workflow(doc, action)
		frappe.db.commit()

		new_state = getattr(updated_doc, "workflow_state", None)
		new_docstatus = updated_doc.docstatus

		changes = []
		if original_state != new_state:
			changes.append(f"State: {original_state} -> {new_state}")
		if before_docstatus != new_docstatus:
			names = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
			changes.append(f"Docstatus: {names.get(before_docstatus)} -> {names.get(new_docstatus)}")

		return json.dumps(
			{
				"doctype": doctype,
				"name": name,
				"status": "workflow_action_applied",
				"action": action,
				"previous_state": original_state,
				"current_state": new_state,
				"docstatus": new_docstatus,
				"changes": changes,
				"next_available_actions": [t["action"] for t in _list_transitions(updated_doc)],
			}
		)

	except frappe.exceptions.WorkflowTransitionError as e:
		return json.dumps(
			{
				"error": str(e),
				"error_type": "workflow_transition_error",
				"doctype": doctype,
				"name": name,
			}
		)

	except frappe.exceptions.WorkflowPermissionError as e:
		return json.dumps(
			{
				"error": str(e),
				"error_type": "workflow_permission_error",
			}
		)

	except frappe.PermissionError:
		return json.dumps({"error": "No permission to modify this document"})

	except Exception as e:
		frappe.log_error(
			title="Run Workflow Error", message=f"Error running workflow on {doctype} '{name}': {e!s}"
		)
		return json.dumps({"error": str(e), "doctype": doctype, "name": name})
