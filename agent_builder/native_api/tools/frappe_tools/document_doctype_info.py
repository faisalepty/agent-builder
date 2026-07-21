# tools/frappe_tools/document_doctype_info.py

import json

import frappe

from agent_builder.native_api.tools.decorator import tool


def _serialize_field(field) -> dict:
	return {
		"fieldname": field.fieldname,
		"label": field.label,
		"fieldtype": field.fieldtype,
		"options": field.options,
		"reqd": field.reqd,
		"read_only": field.read_only,
		"hidden": field.hidden,
		"default": field.default,
		"description": field.description,
	}


@tool(schema_name="frappe_get_doctype_info")
def frappe_get_doctype_info(args: dict, **kwargs) -> str:
	"""Get DocType metadata: fields, child tables, link fields, permissions."""
	doctype = args.get("doctype")

	if not doctype:
		return json.dumps({"error": "doctype is required"})

	try:
		if not frappe.db.exists("DocType", doctype):
			return json.dumps({"error": f"DocType '{doctype}' not found"})

		meta = frappe.get_meta(doctype)
		meta.check_permission("read") if hasattr(meta, "check_permission") else None
		if not frappe.has_permission(doctype, "read"):
			return json.dumps({"error": f"No permission to access DocType '{doctype}'"})

		fields = [_serialize_field(f) for f in meta.fields]

		link_fields = [
			{"fieldname": f.fieldname, "label": f.label, "options": f.options} for f in meta.get_link_fields()
		]

		# Include each child table's own field metadata inline, so the caller
		# can build nested row payloads without a second lookup.
		child_tables = []
		for table_field in meta.get_table_fields():
			child_doctype = table_field.options
			entry = {
				"fieldname": table_field.fieldname,
				"label": table_field.label,
				"options": child_doctype,
				"reqd": table_field.reqd,
				"fields": [],
			}
			if child_doctype and frappe.db.exists("DocType", child_doctype):
				entry["fields"] = [_serialize_field(f) for f in frappe.get_meta(child_doctype).fields]
			child_tables.append(entry)

		return json.dumps(
			{
				"doctype": doctype,
				"module": meta.module,
				"is_submittable": bool(meta.is_submittable),
				"is_tree": bool(meta.is_tree),
				"is_single": bool(meta.issingle),
				"is_child_table": bool(meta.istable),
				"naming_rule": meta.naming_rule,
				"title_field": meta.title_field,
				"fields": fields,
				"link_fields": link_fields,
				"child_tables": child_tables,
			},
			default=str,
		)

	except Exception as e:
		frappe.log_error(title="Get DocType Info Error", message=f"Error getting info for {doctype}: {e!s}")
		return json.dumps({"error": str(e), "doctype": doctype})
