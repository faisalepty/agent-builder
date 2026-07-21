# tools/frappe_tools/document_get.py

import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_get_doc")
def frappe_get_doc(args: dict, **kwargs) -> str:
	"""Retrieve a specific Frappe document by doctype and name."""
	doctype = args.get("doctype")
	name = args.get("name")

	if not doctype or not name:
		return json.dumps({"error": "Both doctype and name are required"})

	try:
		if not frappe.db.exists(doctype, name):
			return json.dumps({"error": f"{doctype} '{name}' not found", "doctype": doctype, "name": name})

		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")

		return json.dumps(
			{
				"doctype": doctype,
				"name": name,
				"data": doc.as_dict(),
			},
			default=str,
		)

	except frappe.PermissionError:
		return json.dumps({"error": f"No permission to read {doctype} '{name}'"})

	except Exception as e:
		frappe.log_error(title="Document Get Error", message=f"Error retrieving {doctype} '{name}': {e!s}")
		return json.dumps({"error": str(e), "doctype": doctype, "name": name})
