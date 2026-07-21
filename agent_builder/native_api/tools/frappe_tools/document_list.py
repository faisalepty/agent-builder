# tools/frappe_tools/document_list.py

import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_get_list")
def frappe_get_list(args: dict, **kwargs) -> str:
	"""Search and list Frappe documents with optional filtering."""
	doctype = args.get("doctype")
	filters = args.get("filters", {})
	fields = args.get("fields") or ["name", "creation", "modified"]
	limit = min(args.get("limit", 20), 1000)
	order_by = args.get("order_by", "creation desc")
	parent_doctype = args.get("parent_doctype")

	if not doctype:
		return json.dumps({"error": "doctype is required"})

	try:
		meta = frappe.get_meta(doctype)

		# Child-table doctypes need parent_doctype passed through for Frappe's
		# permission check, or get_list silently drops all non-name fields.
		if getattr(meta, "istable", 0) and not parent_doctype:
			return json.dumps(
				{
					"error": (
						f"'{doctype}' is a child-table doctype. frappe_get_list requires "
						f"'parent_doctype' to be set for child tables, or field values will "
						f"be silently dropped. Also consider frappe_get_doc on the parent "
						f"record instead — child rows come back fully nested there."
					),
					"error_type": "child_doctype_needs_parent",
				}
			)

		get_list_kwargs = dict(
			filters=filters,
			fields=fields,
			limit=limit,
			order_by=order_by,
			ignore_permissions=False,
		)
		if parent_doctype:
			get_list_kwargs["parent_doctype"] = parent_doctype

		documents = frappe.get_list(doctype, **get_list_kwargs)
		total_count = frappe.db.count(doctype, filters=filters)

		return json.dumps(
			{
				"doctype": doctype,
				"data": documents,
				"count": len(documents),
				"total_count": total_count,
				"has_more": total_count > limit,
				"filters_applied": filters,
			},
			default=str,
		)  # confirmed necessary — see below

	except frappe.PermissionError:
		return json.dumps({"error": f"No permission to read {doctype} documents"})
	except Exception as e:
		frappe.log_error(title="Document List Error", message=f"Error listing {doctype}: {e!s}")
		return json.dumps({"error": str(e), "doctype": doctype})
