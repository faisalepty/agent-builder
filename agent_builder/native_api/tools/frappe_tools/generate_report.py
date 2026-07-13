# tools/frappe_tools/generate_report.py

import json
import time
import frappe
from frappe.utils import add_months, getdate
from agent_builder.native_api.tools.decorator import tool


def _default_filters(filters: dict) -> dict:
    filters = {k: v for k, v in filters.items() if v is not None}

    # ERPNext's shared financial_statements.py (P&L, Balance Sheet, Cash Flow,
    # Gross and Net Profit, etc.) reads period_start_date/period_end_date and
    # from_fiscal_year/to_fiscal_year — NOT from_date/to_date/fiscal_year.
    # Source: erpnext/accounts/report/balance_sheet/balance_sheet.py execute()
    if not filters.get("period_start_date") and filters.get("from_date"):
        filters["period_start_date"] = filters["from_date"]
    if not filters.get("period_end_date") and filters.get("to_date"):
        filters["period_end_date"] = filters["to_date"]

    if not filters.get("period_start_date") and not filters.get("period_end_date"):
        fy = frappe.db.get_value(
            "Fiscal Year", {"disabled": 0}, ["name", "year_start_date", "year_end_date"],
            order_by="year_start_date desc",
        )
        if fy:
            filters["period_start_date"] = str(fy[1])
            filters["period_end_date"] = str(fy[2])
            filters.setdefault("from_fiscal_year", fy[0])
            filters.setdefault("to_fiscal_year", fy[0])
        else:
            today = getdate()
            filters["period_end_date"] = str(today)
            filters["period_start_date"] = str(add_months(today, -12))

    filters.setdefault("filter_based_on", "Date Range")
    filters.setdefault("periodicity", "Yearly")

    if "company" not in filters:
        default_company = frappe.db.get_single_value("Global Defaults", "default_company")
        if default_company:
            filters["company"] = default_company

    return filters


def _run_prepared_or_direct(report_doc, filters: dict, max_wait: int = 120) -> dict:
    """For prepared reports: check for a cached completed run, otherwise queue
    and poll with backoff up to max_wait seconds. For everything else, run directly."""
    from frappe.desk.query_report import run, get_prepared_report_result
    from frappe.core.doctype.prepared_report.prepared_report import (
        get_completed_prepared_report, make_prepared_report,
    )

    is_prepared = getattr(report_doc, "prepared_report", False) and not getattr(
        report_doc, "disable_prepared_report", False
    )

    if not is_prepared:
        return run(report_name=report_doc.name, filters=filters, user=frappe.session.user)

    cached_name = get_completed_prepared_report(
        filters=filters, user=frappe.session.user, report_name=report_doc.name
    )
    if cached_name:
        result = get_prepared_report_result(report_doc, filters, dn=cached_name)
        if result and result.get("result"):
            return {**result, "source": "cached"}

    prepared = make_prepared_report(report_name=report_doc.name, filters=filters)
    prepared_name = prepared.get("name")
    frappe.db.commit()

    elapsed, poll_interval = 0, 2.0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval
        frappe.db.rollback()
        doc = frappe.get_doc("Prepared Report", prepared_name)

        if doc.status == "Completed":
            result = get_prepared_report_result(report_doc, filters, dn=prepared_name)
            if result and result.get("result"):
                return {**result, "source": "background_job", "wait_seconds": int(elapsed)}
        elif doc.status == "Error":
            raise RuntimeError(doc.error_message or "Report generation failed")

        poll_interval = min(poll_interval * 1.5, 15.0)

    return {
        "result": [], "columns": [], "status": "timeout",
        "message": f"Report still generating after {max_wait}s. Retry with the same filters shortly.",
        "prepared_report_name": prepared_name,
    }


@tool(schema_name="frappe_generate_report")
def frappe_generate_report(args: dict = None, **kwargs) -> str:
    """Execute a Query Report or Script Report."""
    # Robust argument extraction to handle different MCP framework behaviors
    if not isinstance(args, dict):
        args = kwargs.get("args", {})
        
    report_name = args.get("report_name") or kwargs.get("report_name")
    filters = args.get("filters") or kwargs.get("filters") or {}
    
    # If filters is still empty, maybe the framework flattened the arguments
    if not filters and isinstance(args, dict) and args:
        filters = {k: v for k, v in args.items() if k != "report_name"}
    if not filters and kwargs:
        filters = {k: v for k, v in kwargs.items() if k not in ["report_name", "args"]}
        
    if not isinstance(filters, dict):
        try:
            filters = json.loads(filters)
        except:
            filters = {}

    if not report_name:
        return json.dumps({"error": "report_name is required"})

    if not frappe.db.exists("Report", report_name):
        return json.dumps({"error": f"Report '{report_name}' not found"})

    try:
        report_doc = frappe.get_doc("Report", report_name)
        report_doc.check_permission("read")

        if report_doc.report_type == "Report Builder":
            return json.dumps({
                "error": "Report Builder reports are not supported. Use a Script Report, "
                         "Query Report, or Custom Report instead.",
            })
        if report_doc.report_type not in ("Query Report", "Script Report"):
            return json.dumps({"error": f"Unsupported report type: {report_doc.report_type}"})

        user_keys = set(filters.keys())
        effective_filters = _default_filters(dict(filters))
        
        # Crucial for reports that read from frappe.form_dict instead of the filters arg
        frappe.local.form_dict.update(effective_filters)

        # GUARDRAIL: Prevent infinite agent loops on empty financial data
        financial_reports = ["Profit and Loss Statement", "Balance Sheet",
                              "Gross and Net Profit Report", "Cash Flow", "Trial Balance"]
        if report_name in financial_reports:
            company = effective_filters.get("company")
            gl_exists = frappe.db.exists("GL Entry", {"company": company, "is_cancelled": 0})
            if not gl_exists:
                fy = frappe.db.get_value(
                    "Fiscal Year", {"disabled": 0}, ["name", "year_start_date", "year_end_date"],
                    order_by="year_start_date desc",
                )
                return json.dumps({
                    "error": "no_financial_data",
                    "report_name": report_name,
                    "company": company,
                    "current_fiscal_year": fy[0] if fy else None,
                    "fiscal_year_range": [str(fy[1]), str(fy[2])] if fy else None,
                    "message": (
                        f"No submitted accounting entries exist for company '{company}'. "
                        f"This is a data-completeness issue, not a filter or tool problem — "
                        f"do not retry with different filters or re-check Sales/Purchase "
                        f"Invoice; GL Entry is authoritative and is confirmed empty. "
                        f"Report this to the user as-is."
                    ),
                }, default=str)

        try:
            result = _run_prepared_or_direct(report_doc, effective_filters)
        except Exception as e:
            error_str = str(e)
            if "mandatory" in error_str.lower():
                return json.dumps({
                    "error": error_str,
                    "report_name": report_name,
                    "hint": f"The report script received these exact filters: {effective_filters}. If it still claims fields are mandatory, the report may be reading from a different source. Use 'frappe_get_list' on 'GL Entry' to fetch data directly."
                })
            raise

        rows = [dict(r) if isinstance(r, dict) else r for r in result.get("result", [])]
        auto_added = {k: v for k, v in effective_filters.items() if k not in user_keys}

        payload = {
            "report_name": report_name,
            "report_type": report_doc.report_type,
            "data": rows,
            "columns": result.get("columns", []),
            "data_count": len(rows),
            "filters_applied": effective_filters,
        }
        if auto_added:
            payload["filters_auto_added"] = auto_added
        if not rows:
            payload["suggestion"] = (
                "Report returned 0 rows — auto-defaulted filters may not match your data. "
                "Retry with explicit filters. If you are checking financial data, verify "
                "underlying GL Entries or Sales Invoices exist for this period using frappe_get_list."
            )

        return json.dumps(payload, default=str)

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to access report '{report_name}'"})
    except Exception as e:
        frappe.log_error(title="Generate Report Error", message=f"Error generating {report_name}: {str(e)}")
        return json.dumps({"error": str(e), "report_name": report_name})