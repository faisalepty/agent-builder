# tools/frappe_tools/document_report_list.py

"""List available Frappe reports with optional filtering by module, type, or name."""

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_list_reports")
def frappe_list_reports(args: dict, **kwargs) -> str:
    """List available Frappe reports, optionally filtered by module, report type, or name substring."""
    module = args.get("module")
    report_type = args.get("report_type")
    name_contains = args.get("name_contains")

    filters = {}
    if module:
        filters["module"] = module
    if report_type:
        filters["report_type"] = report_type
    if name_contains:
        filters["report_name"] = ["like", f"%{name_contains}%"]

    try:
        reports = frappe.get_list(
            "Report",
            filters=filters,
            fields=["name", "report_name", "report_type", "module", "is_standard", "disabled"],
            order_by="report_name",
            ignore_permissions=False,
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