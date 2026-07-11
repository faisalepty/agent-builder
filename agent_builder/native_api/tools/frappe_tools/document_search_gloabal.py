# tools/frappe_tools/document_search_global.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool

COMMON_DOCTYPES = [
    "User", "Contact", "Customer", "Supplier", "Item",
    "Company", "Employee", "Task", "Project",
]


@tool(schema_name="frappe_search_documents")
def frappe_search_documents(args: dict, **kwargs) -> str:
    """Global search by name across common, accessible doctypes."""
    query = args.get("query")
    limit = args.get("limit", 20)

    if not query:
        return json.dumps({"error": "query is required"})

    try:
        results = []
        searched = []

        for doctype in COMMON_DOCTYPES:
            if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
                continue
            searched.append(doctype)

            # frappe.get_list (not get_all) so read permissions are actually enforced
            matches = frappe.get_list(
                doctype,
                filters={"name": ["like", f"%{query}%"]},
                fields=["name"],
                limit=5,
                ignore_permissions=False,
            )
            for m in matches:
                m["doctype"] = doctype
                results.append(m)

        return json.dumps({
            "query": query,
            "results": results[:limit],
            "count": min(len(results), limit),
            "total_found": len(results),
            "searched_doctypes": searched,
        })

    except Exception as e:
        frappe.log_error(title="Search Documents Error", message=f"Error searching '{query}': {str(e)}")
        return json.dumps({"error": str(e)})