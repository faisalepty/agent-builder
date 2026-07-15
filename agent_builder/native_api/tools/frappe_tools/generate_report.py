# tools/frappe_tools/generate_report.py

import hashlib
import json
import time
import frappe
from frappe.utils import add_months, getdate
from agent_builder.native_api.tools.decorator import tool


# A previous version of this tool hardcoded "Sales Analytics"/"Purchase Analytics"
# as permanently unrunnable, reasoning that ERPNext dumps raw data to the browser
# for client-side pivoting. That diagnosis was WRONG — verified against ERPNext's
# actual source (erpnext/selling/report/sales_analytics/sales_analytics.py):
# Analytics.run() returns a perfectly normal 6-tuple
# (columns, data, message, chart, report_summary, skip_total_row).
# The real bug: every live failure supplied 'based_on' (not a real field on this
# report) instead of the two actually-mandatory filters, 'tree_type' and
# 'doc_type' (per the report's own .js: reqd=1, options include
# Customer/Item/Territory/... and Sales Invoice/Quotation/...). When tree_type
# doesn't match one of get_data()'s known branches, self.data is never assigned,
# producing "'Analytics' object has no attribute 'data'" — a missing/invalid
# filter value, not a structural incompatibility. Purchase Analytics imports and
# reuses this exact same Analytics class, so the same fix applies to both.
# Lesson generalized below: instead of guessing or hardcoding filter names/options
# per report, read them from the report's own client-side .js filter definitions
# (frappe.query_reports[name] = {filters: [...]}), which every Query and Script
# Report ships. This fixes the *class* of bug, not just these two reports.

_RETRY_CACHE_PREFIX = "frappe_generate_report:last_call:"
_RETRY_CACHE_TTL = 90  # seconds

# Fallback Link-type filter keys worth checking for existence, used only when a
# report doesn't declare its own Link filters in a way we can parse (e.g. its
# filters live in server-side Python rather than the standard .js block).
_FALLBACK_LINK_FILTER_DOCTYPES = {
    "company": "Company",
    "customer": "Customer",
    "supplier": "Supplier",
    "item": "Item",
    "item_code": "Item",
    "project": "Project",
    "cost_center": "Cost Center",
    "warehouse": "Warehouse",
}

_DATE_FILTER_KEYS = ("from_date", "to_date", "period_start_date", "period_end_date",
                     "posting_date", "transaction_date")

# Kept as a last-resort safety net for a report whose execute() still ends up in
# an inconsistent internal state (e.g. an unrecognized filter value skipped every
# branch of its own logic) even after defaults/validation above. This is no
# longer treated as "unfixable" — the message below reflects the real cause.
_INCOMPLETE_STATE_ERROR_SIGNATURES = (
    "object has no attribute 'data'",
    "object has no attribute 'chart'",
    "object has no attribute 'report_summary'",
)


def _split_top_level_objects(text: str) -> list:
    """Split a JS array-literal's inner text into its top-level {...} object
    bodies, respecting brace nesting (a filter def's 'options: [{...}, {...}]'
    contains braces of its own, so a naive non-nesting regex grabs the wrong
    object — this is what silently broke default/option extraction before)."""
    objs, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(text[start + 1:i])
                start = None
    return objs


def _read_report_filter_defs(report_doc) -> dict:
    """Read a report's own client-side .js filter declarations and return
    {fieldname: {"default": str|None, "options": [str, ...]|None, "reqd": bool}}
    for whatever it declares. Works for both Query and Script Reports — both
    ship a frappe.query_reports[name] = {filters: [...]} block. Best-effort
    only: returns {} on any failure or if no .js file is found, and must never
    block report execution."""
    import os
    import re

    defs = {}
    try:
        report_folder = report_doc.name.lower().replace(" ", "_").replace("-", "_")
        module_folder = (report_doc.module or "").lower().replace(" ", "_")

        for app in frappe.get_installed_apps():
            js_path = os.path.join(
                frappe.get_app_path(app), module_folder, "report", report_folder, f"{report_folder}.js"
            )
            # nosemgrep: frappe-security-file-traversal — path built from frappe.get_app_path
            # + report metadata (module/name from the DB), not from user-supplied input.
            if not os.path.exists(js_path):
                continue

            with open(js_path, encoding="utf-8") as f:
                js_content = f.read()

            filters_start = js_content.find("filters:")
            bracket_start = js_content.find("[", filters_start) if filters_start != -1 else -1
            if bracket_start == -1:
                break

            depth, bracket_end = 0, -1
            for i in range(bracket_start, len(js_content)):
                if js_content[i] == "[":
                    depth += 1
                elif js_content[i] == "]":
                    depth -= 1
                    if depth == 0:
                        bracket_end = i
                        break
            if bracket_end == -1:
                break

            for obj in _split_top_level_objects(js_content[bracket_start + 1:bracket_end]):
                fieldname_match = re.search(r'fieldname:\s*["\']([^"\']+)["\']', obj)
                if not fieldname_match:
                    continue
                entry = {"default": None, "options": None, "reqd": bool(re.search(r"reqd:\s*1", obj))}

                default_match = re.search(r'default:\s*["\']([^"\']+)["\']', obj)
                if default_match:
                    entry["default"] = default_match.group(1)

                # Only treat 'options' as a Select's choice list when it's an array —
                # for Link fields 'options' is a bare doctype string (e.g. "Company"),
                # which this intentionally skips.
                options_match = re.search(r"options:\s*\[(.*?)\]", obj, re.S)
                if options_match:
                    seen, opts = set(), []
                    for q in re.findall(r'["\']([^"\']+)["\']', options_match.group(1)):
                        if q not in seen:
                            seen.add(q)
                            opts.append(q)
                    if opts:
                        entry["options"] = opts

                defs[fieldname_match.group(1)] = entry
            break
    except Exception as e:
        frappe.log_error(title="Generate Report Error", message=f"Filter def extraction failed for {report_doc.name}: {str(e)}")

    return defs


def _apply_declared_defaults(filters: dict, filter_defs: dict) -> dict:
    """Fill in any filter the report itself declares a string-literal default
    for, if it's still missing. (Defaults that are JS expressions rather than
    string literals — e.g. computed dates — aren't parsed here; _default_filters
    already covers dates/company via fiscal year and Global Defaults.)"""
    for fieldname, meta in filter_defs.items():
        if filters.get(fieldname) is None and meta.get("default") is not None:
            filters[fieldname] = meta["default"]
    return filters


def _validate_filter_values(filters: dict, filter_defs: dict = None):
    """Catch bad Link references, invalid Select options, and unparseable dates
    before spending a report execution on them. Select-field validation prefers
    options the report itself declares (filter_defs) over any static guess,
    since valid option sets are report-specific and drift across versions.
    Returns None if clean, otherwise an error payload with concrete suggestions."""
    filter_defs = filter_defs or {}
    errors = []

    for key, doctype in _FALLBACK_LINK_FILTER_DOCTYPES.items():
        value = filters.get(key)
        if not value or isinstance(value, list):
            continue
        if not frappe.db.exists(doctype, value):
            similar = frappe.get_all(doctype, filters={"name": ["like", f"%{value}%"]},
                                      fields=["name"], limit=3)
            suggestion = (
                f"Did you mean: {', '.join(s.name for s in similar)}?" if similar
                else f"Valid {doctype} examples: "
                     f"{', '.join(v.name for v in frappe.get_all(doctype, fields=['name'], limit=5))}"
            )
            errors.append(f"Invalid {key}='{value}': no such {doctype}. {suggestion}")

    for fieldname, meta in filter_defs.items():
        options = meta.get("options")
        value = filters.get(fieldname)
        if options and value and value not in options:
            errors.append(f"Invalid {fieldname}='{value}'. Must be one of: {', '.join(options)}")

    missing_mandatory = [
        fn for fn, meta in filter_defs.items()
        if meta.get("reqd") and filters.get(fn) is None
    ]
    if missing_mandatory:
        errors.append(
            f"Missing mandatory filter(s): {', '.join(missing_mandatory)}. "
            f"This report marks them reqd=1 in its own filter definition."
        )

    for key in _DATE_FILTER_KEYS:
        value = filters.get(key)
        if value:
            try:
                getdate(value)
            except Exception:
                errors.append(f"Invalid {key}='{value}'. Expected format: YYYY-MM-DD")

    if not errors:
        return None
    return {
        "error": "invalid_filter_values",
        "validation_errors": errors,
        "message": "Fix the filter values above and retry — the report was not executed.",
    }


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


def _validate_fiscal_year_coverage(filters: dict):
    """If a company + explicit date range is given but no active Fiscal Year for that
    company covers it, return an actionable error payload instead of letting the
    report raise an opaque 'Date X is not in any active Fiscal Year' exception.
    Confirmed live failure: company='My Company', from_date=2026-01-01 had no
    Fiscal Year record covering it, even though the *global* default Fiscal Year
    (used by _default_filters as a fallback) did exist."""
    company = filters.get("company")
    start = filters.get("period_start_date") or filters.get("from_date")
    end = filters.get("period_end_date") or filters.get("to_date")
    if not (company and start and end):
        return None

    covering = frappe.db.exists(
        "Fiscal Year",
        {"disabled": 0, "year_start_date": ("<=", end), "year_end_date": (">=", start)},
    )
    if covering:
        return None

    available = frappe.db.get_all(
        "Fiscal Year", filters={"disabled": 0}, fields=["name", "year_start_date", "year_end_date"],
        order_by="year_start_date desc", limit=5,
    )
    return {
        "error": "no_fiscal_year_for_range",
        "company": company,
        "requested_range": [str(start), str(end)],
        "available_fiscal_years": [
            {"name": fy.name, "start": str(fy.year_start_date), "end": str(fy.year_end_date)}
            for fy in available
        ],
        "message": (
            f"No active Fiscal Year covers {start} to {end} for company '{company}'. "
            f"This is a configuration/date issue, not a filter-shape problem — do not "
            f"retry with the same dates. Pick a date range within one of the "
            f"available_fiscal_years above, or ask the user to confirm the correct period."
        ),
    }


def _run_prepared_or_direct(report_doc, filters: dict, max_wait: int = 120) -> dict:
    """Check for a cached prepared report, otherwise execute synchronously.
    
    NOTE: We bypass `make_prepared_report` (which enqueues a background job) 
    because this tool runs inside the agent's own background worker. Enqueuing 
    a nested job causes a deadlock where the report sits in the queue until 
    the agent's polling loop times out.
    """
    from frappe.desk.query_report import run, get_prepared_report_result
    from frappe.core.doctype.prepared_report.prepared_report import get_completed_prepared_report

    is_prepared = getattr(report_doc, "prepared_report", False) and not getattr(
        report_doc, "disable_prepared_report", False
    )

    # If it's a prepared report, check if we have a cached version first
    if is_prepared:
        cached_name = get_completed_prepared_report(
            filters=filters, user=frappe.session.user, report_name=report_doc.name
        )
        if cached_name:
            result = get_prepared_report_result(report_doc, filters, dn=cached_name)
            if result and result.get("result"):
                return {**result, "source": "cached"}

    # CRITICAL FIX: Frappe's `run()` function intentionally returns empty data 
    # if `prepared_report` is True and no cached report is found. It expects the 
    # UI to trigger a background job. To force synchronous execution inside the 
    # agent's worker, we temporarily disable the flag in memory.
    original_prepared_flag = report_doc.prepared_report
    report_doc.prepared_report = 0

    try:
        result = run(
            report_name=report_doc.name, 
            filters=filters, 
            user=frappe.session.user,
            is_tree=getattr(report_doc, "is_tree", 0),
            parent_field=getattr(report_doc, "parent_field", None),
        )
    finally:
        # Restore the original flag to avoid unintended side effects 
        # on the doc object later in the request lifecycle.
        report_doc.prepared_report = original_prepared_flag

    result["source"] = "synchronous"
    return result

def _extract_args(args, kwargs):
    """Normalize (report_name, filters) regardless of whether the MCP framework
    nested them under 'args', flattened them into kwargs, or passed filters as a
    JSON string."""
    payload = args if isinstance(args, dict) else kwargs.get("args") or {}
    report_name = payload.get("report_name") or kwargs.get("report_name")
    filters = payload.get("filters")
    if filters is None:
        filters = kwargs.get("filters")
    if filters is None:
        # Framework flattened the arguments directly into payload/kwargs
        flat = {k: v for k, v in {**kwargs, **payload}.items()
                if k not in ("report_name", "filters", "args")}
        filters = flat or {}
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (TypeError, ValueError):
            filters = {}
    if not isinstance(filters, dict):
        filters = {}
    return report_name, filters


@tool(schema_name="frappe_generate_report")
def frappe_generate_report(args: dict = None, **kwargs) -> str:
    """Execute a Query Report or Script Report."""
    report_name, filters = _extract_args(args, kwargs)

    if not report_name:
        return json.dumps({"error": "report_name is required"})

    if not frappe.db.exists("Report", report_name):
        return json.dumps({"error": f"Report '{report_name}' not found"})

    # Short-circuit identical retries within a short window: several live sessions
    # showed the same (report_name, filters) pair retried after an identical failure,
    # burning tool calls on a result that cannot change.
    cache_key = _RETRY_CACHE_PREFIX + hashlib.sha256(
        f"{frappe.session.user}:{report_name}:{json.dumps(filters, sort_keys=True, default=str)}".encode()
    ).hexdigest()
    cached_error = frappe.cache().get_value(cache_key)
    if cached_error:
        return json.dumps({
            "error": "identical_retry_detected",
            "report_name": report_name,
            "previous_error": cached_error,
            "message": (
                "This exact report_name + filters combination was already attempted "
                f"in the last {_RETRY_CACHE_TTL}s and failed with the error above. "
                "Change the filters meaningfully or stop; retrying identically will not help."
            ),
        }, default=str)

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

        # Read this report's own declared filter defaults/options once, and use
        # them both to fill in missing values and to validate what's there —
        # generalizes across any report shaped like Sales/Purchase Analytics
        # instead of guessing or hardcoding per report name.
        filter_defs = _read_report_filter_defs(report_doc)
        effective_filters = _apply_declared_defaults(effective_filters, filter_defs)

        # GUARDRAIL: Catch bad Link references / invalid Select options / bad dates /
        # missing report-declared mandatory filters before spending an execution on them.
        validation_error = _validate_filter_values(effective_filters, filter_defs)
        if validation_error:
            frappe.cache().set_value(cache_key, validation_error, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(validation_error, default=str)

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

        # GUARDRAIL: Fail fast on a company/date range not covered by any Fiscal Year,
        # rather than letting the report raise its own opaque exception mid-execution.
        fy_error = _validate_fiscal_year_coverage(effective_filters)
        if fy_error:
            frappe.cache().set_value(cache_key, fy_error, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(fy_error, default=str)

        try:
            result = _run_prepared_or_direct(report_doc, effective_filters)
        except KeyError as e:
            missing_key = str(e).strip("'\"")
            payload = {
                "error": f"missing_required_filter:{missing_key}",
                "report_name": report_name,
                "filters_sent": effective_filters,
                "hint": (
                    f"The report script reads filters['{missing_key}'] directly and has no "
                    f"default for it. Supply '{missing_key}' explicitly and retry once. If "
                    f"you don't know the valid values, check the report's standard filter "
                    f"panel in the Frappe Desk UI or the report's .json filter definitions."
                ),
            }
            frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(payload, default=str)
        except Exception as e:
            error_str = str(e)
            if any(sig in error_str for sig in _INCOMPLETE_STATE_ERROR_SIGNATURES):
                declared = {fn: meta.get("options") for fn, meta in filter_defs.items() if meta.get("options")}
                payload = {
                    "error": "report_internal_state_incomplete",
                    "report_name": report_name,
                    "filters_sent": effective_filters,
                    "message": (
                        f"'{report_name}' raised {error_str}. This typically means a Select-type "
                        f"filter value didn't match any branch the report's own execute() checks "
                        f"for, so it never finished building its result. This is fixable — it is "
                        f"not a structural limitation of this tool. Check filters_sent against "
                        f"this report's actual valid options below and retry with a matching value."
                    ),
                    "declared_filter_options": declared or None,
                }
                frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
                return json.dumps(payload, default=str)
            if "not in any active fiscal year" in error_str.lower():
                payload = {
                    "error": "no_fiscal_year_for_range",
                    "report_name": report_name,
                    "message": (
                        f"{error_str}. This is a configuration/date issue, not a filter-shape "
                        f"problem — do not retry with the same dates. Pick a different date "
                        f"range or confirm the correct fiscal year with the user."
                    ),
                }
                frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
                return json.dumps(payload, default=str)
            if "mandatory" in error_str.lower():
                payload = {
                    "error": error_str,
                    "report_name": report_name,
                    "hint": f"The report script received these exact filters: {effective_filters}. If it still claims fields are mandatory, the report may be reading from a different source. Use 'frappe_get_list' on 'GL Entry' to fetch data directly."
                }
                frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
                return json.dumps(payload, default=str)
            frappe.cache().set_value(cache_key, {"error": error_str}, expires_in_sec=_RETRY_CACHE_TTL)
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
        if result.get("message"):
            payload["message"] = result["message"]
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
        frappe.cache().set_value(cache_key, {"error": str(e)}, expires_in_sec=_RETRY_CACHE_TTL)
        return json.dumps({"error": str(e), "report_name": report_name})