from typing import Dict, Any
import frappe
from frappe import _
from agent_builder.native_api.tools.decorator import tool

def generate_report(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute report generation"""
    try:
        # Import the report implementation
        from .report_tools import ReportTools

        # Execute report using existing implementation
        return ReportTools.execute_report(
            report_name=arguments.get("report_name"),
            filters=arguments.get("filters", {}),
            format=arguments.get("format", "json"),
        )

    except Exception as e:
        frappe.log_error(title=_("Generate Report Error"), message=f"Error generating report: {str(e)}")

        return {"success": False, "error": str(e)}