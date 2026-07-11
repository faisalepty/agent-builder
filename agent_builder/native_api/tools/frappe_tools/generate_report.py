# tools/frappe_tools/generate_report.py

import json
import time
import frappe
from frappe.utils import add_months, getdate
from agent_builder.native_api.tools.decorator import tool


def _default_filters(filters: dict) -> dict:
    """Fill in from_date/to_date (fiscal year, falling back to trailing 12 months)
    and default company if missing — the two defaults that actually prevent
    'MandatoryError'-style report failures often enough to be worth keeping."""
    filters = {k: v for k, v in filters.items() if v is not None}

    if not filters.get("from_date") and not filters.get("to_date"):
        fy = frappe.db.get_value(
            "Fiscal Year", {"disabled": 0}, ["year_start_date", "year_end_date"],
            order_by="year_start_date desc",
        )
        if fy:
            filters["from_date"], filters["to_date"] = str(fy[0]), str(fy[1])
        else:
            today = getdate()
            filters["to_date"] = str(today)
            filters["from_date"] = str(add_months(today, -12))
    elif filters.get("from_date") and not filters.get("to_date"):
        filters["to_date"] = str(getdate())
    elif filters.get("to_date") and not filters.get("from_date"):
        filters["from_date"] = str(add_months(getdate(filters["to_date"]), -12))

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
def frappe_generate_report(args: dict, **kwargs) -> str:
    """Execute a Query Report or Script Report."""
    report_name = args.get("report_name")
    filters = args.get("filters", {})

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

        result = _run_prepared_or_direct(report_doc, effective_filters)
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
                "Retry with explicit filters."
            )

        return json.dumps(payload)

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to access report '{report_name}'"})
    except Exception as e:
        frappe.log_error(title="Generate Report Error", message=f"Error generating {report_name}: {str(e)}")
        return json.dumps({"error": str(e), "report_name": report_name})