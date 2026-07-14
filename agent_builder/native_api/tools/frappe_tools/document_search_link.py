# tools/frappe_tools/document_search_link.py

import json
import frappe
from frappe.desk.search import search_link
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_search_link")
def frappe_search_link(args: dict, **kwargs) -> str:
    """Fuzzy-search for valid values of a link field (e.g. resolving a customer name to its exact record name)."""
    doctype = args.get("doctype")
    query = args.get("query")
    filters = args.get("filters", {})

    if not doctype or not query:
        return json.dumps({"error": "doctype and query are required"})

    try:
        if not frappe.db.exists("DocType", doctype):
            return json.dumps({"error": f"DocType '{doctype}' not found"})
        if not frappe.has_permission(doctype, "read"):
            return json.dumps({"error": f"No read permission for DocType '{doctype}'"})

        results = search_link(doctype=doctype, txt=query, filters=filters)

        return json.dumps({
            "doctype": doctype,
            "query": query,
            "results": results,
            "count": len(results),
            "filters_applied": filters,
        })

    except Exception as e:
        frappe.log_error(title="Search Link Error", message=f"Error searching link '{doctype}': {str(e)}")
        return json.dumps({"error": str(e), "doctype": doctype})