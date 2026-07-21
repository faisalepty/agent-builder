# tools/frappe_tools/document_submit.py

import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_submit_doc")
def frappe_submit_doc(args: dict, **kwargs) -> str:
	"""Submit a draft document. Only works on documents in draft state (docstatus=0)."""
	doctype = args.get("doctype")
	name = args.get("name")

	if not doctype or not name:
		return json.dumps({"error": "Both doctype and name are required"})

	try:
		if not frappe.db.exists(doctype, name):
			return json.dumps({"error": f"{doctype} '{name}' not found", "doctype": doctype, "name": name})

		meta = frappe.get_meta(doctype)
		if not getattr(meta, "is_submittable", False):
			return json.dumps(
				{
					"error": f"{doctype} is not a submittable DocType",
					"doctype": doctype,
				}
			)

		doc = frappe.get_doc(doctype, name)
		doc.check_permission("submit")

		current_docstatus = doc.docstatus
		if current_docstatus != 0:
			state = {1: "submitted", 2: "cancelled"}.get(current_docstatus, "unknown")
			return json.dumps(
				{
					"error": f"Cannot submit {state} document {doctype} '{name}'. Only draft documents can be submitted.",
					"docstatus": current_docstatus,
					"doctype": doctype,
					"name": name,
				}
			)

		doc.submit()
		frappe.db.commit()
		doc.reload()

		return json.dumps(
			{
				"name": doc.name,
				"doctype": doctype,
				"docstatus": doc.docstatus,
				"status": "submitted",
				"modified": str(doc.modified),
			}
		)

	except frappe.PermissionError:
		return json.dumps({"error": "No permission to submit this document"})

	except frappe.ValidationError as e:
		return json.dumps({"error": f"Validation failed: {e!s}"})

	except Exception as e:
		frappe.log_error(title="Document Submit Error", message=f"Error submitting {doctype} '{name}': {e!s}")
		return json.dumps({"error": str(e), "doctype": doctype, "name": name})
