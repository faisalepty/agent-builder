# tools/frappe_tools/document_search_global.py

"""Global search by name across doctypes.

The default doctype list covers the most commonly name-searched records.
Use the 'doctypes' parameter to search additional or different doctypes.
"""

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


# Doctypes most commonly searched by name. Kept focused to avoid slow queries
# and irrelevant results. Use the 'doctypes' parameter to add more.
DEFAULT_SEARCH_DOCTYPES = [
    # People & Organizations
    "User", "Contact", "Customer", "Supplier", "Employee",
    # Items & Products
    "Item", "Product Bundle", "BOM",
    # Transactions
    "Sales Order", "Purchase Order", "Quotation",
    "Sales Invoice", "Purchase Invoice",
    "Delivery Note", "Purchase Receipt",
    # CRM
    "Lead", "Opportunity",
    # Projects & Tasks
    "Project", "Task",
    # Company structure
    "Company", "Cost Center", "Warehouse",
    # Accounting
    "Account",
]


@tool(schema_name="frappe_search_documents")
def frappe_search_documents(args: dict, **kwargs) -> str:
    """Search by name across doctypes. Use 'doctypes' param to specify which doctypes to search (default covers common ones). Use frappe_get_list when you know the doctype."""
    query = args.get("query")
    limit = args.get("limit", 20)
    doctypes = args.get("doctypes")  # Override default list

    if not query:
        return json.dumps({"error": "query is required"})

    # Determine which doctypes to search
    if doctypes:
        if isinstance(doctypes, str):
            doctypes = [d.strip() for d in doctypes.split(",")]
    else:
        doctypes = DEFAULT_SEARCH_DOCTYPES

    try:
        results = []
        searched = []

        for doctype in doctypes:
            if not frappe.db.exists("DocType", doctype):
                continue
            if not frappe.has_permission(doctype, "read"):
                continue
            searched.append(doctype)

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