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

    if not doctype:
        return json.dumps({"error": "doctype is required"})

    try:
        documents = frappe.get_list(
            doctype,
            filters=filters,
            fields=fields,
            limit=limit,
            order_by=order_by,
            ignore_permissions=False,  # enforce the logged-in user's own permissions
        )

        total_count = frappe.db.count(doctype, filters=filters)

        return json.dumps({
            "doctype": doctype,
            "data": documents,
            "count": len(documents),
            "total_count": total_count,
            "has_more": total_count > limit,
            "filters_applied": filters,
        })

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to read {doctype} documents"})

    except Exception as e:
        frappe.log_error(title="Document List Error", message=f"Error listing {doctype}: {str(e)}")
        return json.dumps({"error": str(e), "doctype": doctype})