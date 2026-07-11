# tools/frappe_tools/document_report_list.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_list_reports")
def frappe_list_reports(args: dict, **kwargs) -> str:
    """List available Frappe reports, optionally filtered by module or report type."""
    module = args.get("module")
    report_type = args.get("report_type")

    filters = {}
    if module:
        filters["module"] = module
    if report_type:
        filters["report_type"] = report_type

    try:
        reports = frappe.get_list(
            "Report",
            filters=filters,
            fields=["name", "report_name", "report_type", "module", "is_standard", "disabled"],
            order_by="report_name",
            ignore_permissions=False,  # enforce the logged-in user's own permissions
        )

        return json.dumps({
            "reports": reports,
            "count": len(reports),
            "filters_applied": filters,
        })

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to list reports"})
    except Exception as e:
        frappe.log_error(title="List Reports Error", message=f"Error listing reports: {str(e)}")
        return json.dumps({"error": str(e)})