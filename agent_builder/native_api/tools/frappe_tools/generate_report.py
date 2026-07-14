"""Execute any Frappe report by calling frappe.desk.query_report.run() directly
— the same function the web UI uses. No background jobs, no file I/O, no polling.

Pre-execution: auto-defaults fiscal year dates and company, reads report's own
.js filter definitions for mandatory fields and options, validates Link field
values exist, validates Select field values against declared options, catches
fiscal year coverage gaps before execution, caches identical failed calls to
prevent agent loops.
"""

import hashlib
import json
import frappe
from frappe.utils import add_months, getdate
from agent_builder.native_api.tools.decorator import tool


_RETRY_CACHE_PREFIX = "frappe_generate_report:last_call:"
_RETRY_CACHE_TTL = 90

_LINK_FILTER_DOCTYPES = {
    "company": "Company",
    "customer": "Customer",
    "supplier": "Supplier",
    "item": "Item",
    "item_code": "Item",
    "project": "Project",
    "cost_center": "Cost Center",
    "warehouse": "Warehouse",
    "employee": "Employee",
}

_DATE_FILTER_KEYS = (
    "from_date", "to_date", "period_start_date", "period_end_date",
    "posting_date", "transaction_date", "start_date", "end_date",
)

_FINANCIAL_STATEMENT_REPORTS = {
    "Profit and Loss Statement",
    "Balance Sheet",
    "Cash Flow",
    "Gross and Net Profit Report",
    "Trial Balance",
}

_INCOMPLETE_STATE_SIGNATURES = (
    "object has no attribute 'data'",
    "object has no attribute 'chart'",
    "object has no attribute 'report_summary'",
)


def _split_top_level_objects(text: str) -> list:
    """Split JS array literal into top-level {...} bodies, respecting nesting."""
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
    """Read report's client-side .js filter declarations.
    Returns {fieldname: {"default": str|None, "options": [str]|None, "reqd": bool}}.
    Best-effort: returns {} for Report Builder or on any failure."""
    import os
    import re

    defs = {}
    try:
        report_folder = report_doc.name.lower().replace(" ", "_").replace("-", "_")
        module_folder = (report_doc.module or "").lower().replace(" ", "_")

        for app in frappe.get_installed_apps():
            js_path = os.path.join(
                frappe.get_app_path(app), module_folder, "report",
                report_folder, f"{report_folder}.js",
            )
            if not os.path.exists(js_path):
                continue

            with open(js_path, encoding="utf-8") as f:
                js_content = f.read()

            filters_start = js_content.find("filters:")
            if filters_start == -1:
                break
            bracket_start = js_content.find("[", filters_start)
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

                # Only parse options as array for Select fields, not Link fields
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
        frappe.log_error(
            title="Report Filter Def Extraction",
            message=f"Failed for {report_doc.name}: {e}",
        )
    return defs


def _apply_declared_defaults(filters: dict, filter_defs: dict) -> dict:
    """Fill missing filters from report's declared defaults."""
    for fieldname, meta in filter_defs.items():
        if filters.get(fieldname) is None and meta.get("default") is not None:
            filters[fieldname] = meta["default"]
    return filters


def _validate_filter_values(filters: dict, filter_defs: dict = None) -> dict | None:
    """Validate Link refs, Select options, dates, mandatory fields.
    Returns None if clean, else error payload."""
    filter_defs = filter_defs or {}
    errors = []

    for key, doctype in _LINK_FILTER_DOCTYPES.items():
        value = filters.get(key)
        if not value or isinstance(value, list):
            continue
        if not frappe.db.exists(doctype, value):
            similar = frappe.get_all(
                doctype, filters={"name": ["like", f"%{value}%"]},
                fields=["name"], limit=3,
            )
            suggestion = (
                f"Did you mean: {', '.join(s.name for s in similar)}?"
                if similar
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
        errors.append(f"Missing mandatory filter(s): {', '.join(missing_mandatory)}.")

    for key in _DATE_FILTER_KEYS:
        value = filters.get(key)
        if value:
            try:
                getdate(value)
            except Exception:
                errors.append(f"Invalid {key}='{value}'. Expected YYYY-MM-DD.")

    if not errors:
        return None
    return {
        "error": "invalid_filter_values",
        "validation_errors": errors,
        "message": "Fix filter values and retry.",
    }


def _default_filters(filters: dict) -> dict:
    """Apply standard defaults: fiscal year dates, company, filter_based_on."""
    filters = {k: v for k, v in filters.items() if v is not None}

    if not filters.get("period_start_date") and filters.get("from_date"):
        filters["period_start_date"] = filters["from_date"]
    if not filters.get("period_end_date") and filters.get("to_date"):
        filters["period_end_date"] = filters["to_date"]

    if not filters.get("period_start_date") and not filters.get("period_end_date"):
        fy = frappe.db.get_value(
            "Fiscal Year", {"disabled": 0},
            ["name", "year_start_date", "year_end_date"],
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


def _validate_fiscal_year_coverage(filters: dict) -> dict | None:
    """Fail fast if no Fiscal Year covers the given date range."""
    company = filters.get("company")
    start = filters.get("period_start_date") or filters.get("from_date")
    end = filters.get("period_end_date") or filters.get("to_date")
    if not (company and start and end):
        return None
    if frappe.db.exists(
        "Fiscal Year",
        {"disabled": 0, "year_start_date": ("<=", end), "year_end_date": (">=", start)},
    ):
        return None
    available = frappe.db.get_all(
        "Fiscal Year", filters={"disabled": 0},
        fields=["name", "year_start_date", "year_end_date"],
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
        "message": f"No active Fiscal Year covers {start} to {end} for '{company}'. "
                   f"Pick a date range within available_fiscal_years.",
    }


def _extract_args(args, kwargs):
    """Normalize (report_name, filters) from various MCP framework call styles."""
    payload = args if isinstance(args, dict) else kwargs.get("args") or {}
    report_name = payload.get("report_name") or kwargs.get("report_name")
    filters = payload.get("filters")
    if filters is None:
        filters = kwargs.get("filters")
    if filters is None:
        flat = {
            k: v for k, v in {**kwargs, **payload}.items()
            if k not in ("report_name", "filters", "args")
        }
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
    """Execute any Frappe report and return its data."""
    report_name, filters = _extract_args(args, kwargs)

    if not report_name:
        return json.dumps({"error": "report_name is required"})

    if not frappe.db.exists("Report", report_name):
        return json.dumps({"error": f"Report '{report_name}' not found"})

    # Prevent identical failed calls in a loop
    cache_key = _RETRY_CACHE_PREFIX + hashlib.sha256(
        f"{frappe.session.user}:{report_name}:{json.dumps(filters, sort_keys=True, default=str)}".encode()
    ).hexdigest()
    cached_error = frappe.cache().get_value(cache_key)
    if cached_error:
        return json.dumps({
            "error": "identical_retry_detected",
            "report_name": report_name,
            "previous_error": cached_error,
            "message": f"This exact report+filters was tried in the last {_RETRY_CACHE_TTL}s and failed. Change filters or stop.",
        }, default=str)

    effective_filters = None
    filter_defs = {}

    try:
        report_doc = frappe.get_doc("Report", report_name)
        report_doc.check_permission("read")

        user_keys = set(filters.keys())
        effective_filters = _default_filters(dict(filters))

        # Read and apply report's own filter definitions (no-op for Report Builder)
        filter_defs = _read_report_filter_defs(report_doc)
        effective_filters = _apply_declared_defaults(effective_filters, filter_defs)

        # Validate before executing
        validation_error = _validate_filter_values(effective_filters, filter_defs)
        if validation_error:
            frappe.cache().set_value(cache_key, validation_error, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(validation_error, default=str)

        # Only inject into form_dict for Script Reports — they're the ones
        # that read from frappe.form_dict instead of the filters argument.
        # Report Builder and Query Reports don't need this.
        if report_doc.report_type == "Script Report":
            frappe.local.form_dict.update(effective_filters)

        # Guardrail: no GL data for financial statements
        if report_name in _FINANCIAL_STATEMENT_REPORTS:
            company = effective_filters.get("company")
            if not frappe.db.exists("GL Entry", {"company": company, "is_cancelled": 0}):
                payload = {
                    "error": "no_financial_data",
                    "report_name": report_name,
                    "company": company,
                    "message": f"No submitted GL Entries for '{company}'. This is a data issue, not a filter problem.",
                }
                frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
                return json.dumps(payload, default=str)

        # Guardrail: fiscal year coverage
        fy_error = _validate_fiscal_year_coverage(effective_filters)
        if fy_error:
            frappe.cache().set_value(cache_key, fy_error, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(fy_error, default=str)

        # ────────────────────────────────────────────────────────
        # Execute — same call the Frappe web UI makes.
        # No background jobs, no file I/O, no polling, no hooks.
        # ────────────────────────────────────────────────────────
        from frappe.desk.query_report import run

        result = run(
            report_name=report_doc.name,
            filters=effective_filters,
            user=frappe.session.user,
            is_tree=getattr(report_doc, "is_tree", 0),
            parent_field=getattr(report_doc, "parent_field", None),
        )

        # ────────────────────────────────────────────────────────

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
                "Report returned 0 rows. Auto-defaulted filters may not match your data. "
                "Try explicit filters, or verify data exists via frappe_get_list."
            )
        return json.dumps(payload, default=str)

    except KeyError as e:
        missing_key = str(e).strip("'\"")
        payload = {
            "error": f"missing_required_filter:{missing_key}",
            "report_name": report_name,
            "filters_sent": effective_filters or filters,
            "hint": f"Report reads filters['{missing_key}'] with no default. Supply it explicitly.",
        }
        frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
        return json.dumps(payload, default=str)

    except Exception as e:
        error_str = str(e)

        if any(sig in error_str for sig in _INCOMPLETE_STATE_SIGNATURES):
            declared = {fn: meta.get("options") for fn, meta in filter_defs.items() if meta.get("options")}
            payload = {
                "error": "report_internal_state_incomplete",
                "report_name": report_name,
                "filters_sent": effective_filters or filters,
                "message": f"'{report_name}' raised {error_str}. A filter value didn't match any branch in execute().",
                "declared_filter_options": declared or None,
            }
            frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(payload, default=str)

        if "not in any active fiscal year" in error_str.lower():
            payload = {
                "error": "no_fiscal_year_for_range",
                "report_name": report_name,
                "message": f"{error_str}. Pick a different date range.",
            }
            frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(payload, default=str)

        if "mandatory" in error_str.lower():
            payload = {
                "error": error_str,
                "report_name": report_name,
                "hint": (
                    f"The report script received these exact filters: {effective_filters or filters}. "
                    f"If it still claims fields are mandatory, the report may be reading from a different source. "
                    f"Use 'frappe_get_list' on 'GL Entry' to fetch data directly."
                ),
            }
            frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(payload, default=str)

        if isinstance(e, frappe.PermissionError):
            return json.dumps({"error": f"No permission to access report '{report_name}'"})

        frappe.log_error(title="Generate Report Error", message=f"{report_name}: {e}")
        frappe.cache().set_value(cache_key, {"error": error_str}, expires_in_sec=_RETRY_CACHE_TTL)
        return json.dumps({"error": error_str, "report_name": report_name})