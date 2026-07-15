# tools/frappe_tools/generate_report.py

import hashlib
import json
import time
import frappe
from collections import Counter
from frappe.utils import add_months, getdate
from agent_builder.native_api.tools.decorator import tool


# ── NEW: AI efficiency constants ──────────────────────────────────────────
_MAX_HARD_ROWS = 2000       # Absolute ceiling — never return more than this
_DEFAULT_MAX_ROWS = 200     # Sensible default for AI context windows
_PREVIEW_SAMPLE_ROWS = 5    # Rows returned in preview_mode
# ──────────────────────────────────────────────────────────────────────────

_RETRY_CACHE_PREFIX = "frappe_generate_report:last_call:"
_RETRY_CACHE_TTL = 90

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

_INCOMPLETE_STATE_ERROR_SIGNATURES = (
    "object has no attribute 'data'",
    "object has no attribute 'chart'",
    "object has no attribute 'report_summary'",
)


# ── NEW: Columnar serialization ───────────────────────────────────────────
def _rows_to_columnar(rows: list) -> dict:
    """Convert list-of-dicts → {fields: [...], rows: [[...], ...]}.

    Before (10 rows × 6 cols ≈ 1,200 tokens):
      [{"name":"A","qty":1,"rate":100,...}, ...]
    After  (≈ 500 tokens):
      {"fields":["name","qty","rate",...], "rows":[["A",1,100,...], ...]}
    """
    if not rows:
        return {"fields": [], "rows": []}
    if isinstance(rows[0], dict):
        fields = list(rows[0].keys())
        data = [[r.get(f) for f in fields] for r in rows]
    else:
        fields = []
        data = rows
    return {"fields": fields, "rows": data}


def _columnar_to_rows(columnar: dict) -> list:
    """Reverse: columnar → list-of-dicts (for backward-compat if needed)."""
    fields = columnar.get("fields", [])
    return [dict(zip(fields, row)) for row in columnar.get("rows", [])]


# ── NEW: Lightweight summarization ────────────────────────────────────────
def _summarize_columns(rows: list, fields: list) -> dict:
    """When we truncate, give the AI aggregate stats so it can still answer
    "how much?" / "what's the range?" questions without re-querying."""
    summary = {}
    for i, field in enumerate(fields):
        values = [r[i] for r in rows if i < len(r) and r[i] is not None]
        if not values:
            summary[field] = {"count": 0, "null_count": len(rows)}
            continue

        # Try numeric
        numeric_vals = []
        for v in values:
            try:
                numeric_vals.append(float(v))
            except (TypeError, ValueError):
                break

        if len(numeric_vals) == len(values):
            summary[field] = {
                "type": "numeric",
                "min": min(numeric_vals),
                "max": max(numeric_vals),
                "sum": sum(numeric_vals),
                "count": len(numeric_vals),
            }
        else:
            counter = Counter(str(v) for v in values)
            summary[field] = {
                "type": "categorical",
                "distinct_count": len(counter),
                "top_values": counter.most_common(5),
                "count": len(values),
            }
    return summary


def _extract_column_names(columns_from_report: list) -> list:
    """Frappe report columns come in varied shapes:
      [{"label":"Name","fieldname":"name","fieldtype":"Data"}, ...]
      or just ["name", ...]
    Normalise to a flat list of fieldname strings."""
    names = []
    for col in columns_from_report:
        if isinstance(col, dict):
            names.append(col.get("fieldname") or col.get("label") or str(col))
        else:
            names.append(str(col))
    return names
# ──────────────────────────────────────────────────────────────────────────


# ── (All existing helpers unchanged: _split_top_level_objects,
#    _read_report_filter_defs, _apply_declared_defaults,
#    _validate_filter_values, _default_filters,
#    _validate_fiscal_year_coverage, _run_prepared_or_direct,
#    _extract_args — keeping their existing implementations) ────────────────

def _split_top_level_objects(text: str) -> list:
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
    import os, re
    defs = {}
    try:
        report_folder = report_doc.name.lower().replace(" ", "_").replace("-", "_")
        module_folder = (report_doc.module or "").lower().replace(" ", "_")
        for app in frappe.get_installed_apps():
            js_path = os.path.join(
                frappe.get_app_path(app), module_folder, "report", report_folder, f"{report_folder}.js"
            )
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
    for fieldname, meta in filter_defs.items():
        if filters.get(fieldname) is None and meta.get("default") is not None:
            filters[fieldname] = meta["default"]
    return filters


def _validate_filter_values(filters: dict, filter_defs: dict = None):
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
            f"Pick a date range within one of the available_fiscal_years above."
        ),
    }


def _run_prepared_or_direct(report_doc, filters: dict, max_wait: int = 120) -> dict:
    from frappe.desk.query_report import run, get_prepared_report_result
    from frappe.core.doctype.prepared_report.prepared_report import get_completed_prepared_report

    is_prepared = getattr(report_doc, "prepared_report", False) and not getattr(
        report_doc, "disable_prepared_report", False
    )
    if is_prepared:
        cached_name = get_completed_prepared_report(
            filters=filters, user=frappe.session.user, report_name=report_doc.name
        )
        if cached_name:
            result = get_prepared_report_result(report_doc, filters, dn=cached_name)
            if result and result.get("result"):
                return {**result, "source": "cached"}

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
        report_doc.prepared_report = original_prepared_flag

    result["source"] = "synchronous"
    return result


def _extract_args(args, kwargs):
    payload = args if isinstance(args, dict) else kwargs.get("args") or {}
    report_name = payload.get("report_name") or kwargs.get("report_name")
    filters = payload.get("filters")
    if filters is None:
        filters = kwargs.get("filters")
    if filters is None:
        flat = {k: v for k, v in {**kwargs, **payload}.items()
                if k not in ("report_name", "filters", "args",
                             "max_rows", "offset", "preview_mode", "columns")}
        filters = flat or {}
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (TypeError, ValueError):
            filters = {}
    if not isinstance(filters, dict):
        filters = {}

    # ── NEW: Extract pagination/efficiency parameters ─────────────────────
    max_rows = payload.get("max_rows") or kwargs.get("max_rows") or _DEFAULT_MAX_ROWS
    try:
        max_rows = int(max_rows)
    except (TypeError, ValueError):
        max_rows = _DEFAULT_MAX_ROWS
    max_rows = min(max_rows, _MAX_HARD_ROWS)  # hard cap

    offset = payload.get("offset") or kwargs.get("offset") or 0
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0

    preview_mode = payload.get("preview_mode") or kwargs.get("preview_mode") or False
    if isinstance(preview_mode, str):
        preview_mode = preview_mode.lower() in ("true", "1", "yes")

    requested_columns = payload.get("columns") or kwargs.get("columns")
    if isinstance(requested_columns, str):
        try:
            requested_columns = json.loads(requested_columns)
        except (TypeError, ValueError):
            requested_columns = None

    return report_name, filters, max_rows, offset, preview_mode, requested_columns
    # ──────────────────────────────────────────────────────────────────────


@tool(schema_name="frappe_generate_report")
def frappe_generate_report(args: dict = None, **kwargs) -> str:
    """Execute a Query Report or Script Report.

    AI-efficiency parameters (pass alongside report_name & filters):
      max_rows       – Max rows to return (default 200, hard cap 2000).
                       Use offset to paginate through larger results.
      offset         – Starting row index for pagination (default 0).
      preview_mode   – If true, returns only column schema + total count
                       + a 5-row sample. Ideal for discovering a report's
                       shape before pulling full data. (default false)
      columns        – JSON array of fieldnames to include. Omits all
                       others, reducing token cost. (default: all columns)
    """

    report_name, filters, max_rows, offset, preview_mode, requested_columns = \
        _extract_args(args, kwargs)

    if not report_name:
        return json.dumps({"error": "report_name is required"})

    if not frappe.db.exists("Report", report_name):
        return json.dumps({"error": f"Report '{report_name}' not found"})

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

        filter_defs = _read_report_filter_defs(report_doc)
        effective_filters = _apply_declared_defaults(effective_filters, filter_defs)

        validation_error = _validate_filter_values(effective_filters, filter_defs)
        if validation_error:
            frappe.cache().set_value(cache_key, validation_error, expires_in_sec=_RETRY_CACHE_TTL)
            return json.dumps(validation_error, default=str)

        frappe.local.form_dict.update(effective_filters)

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
                        f"This is a data-completeness issue — do not retry with different filters."
                    ),
                }, default=str)

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
                    f"default for it. Supply '{missing_key}' explicitly and retry once."
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
                        f"'{report_name}' raised {error_str}. A Select-type filter value "
                        f"didn't match any branch the report's execute() checks for."
                    ),
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
                    "hint": f"The report script received: {effective_filters}. If it still claims fields are mandatory, use 'frappe_get_list' on 'GL Entry' instead."
                }
                frappe.cache().set_value(cache_key, payload, expires_in_sec=_RETRY_CACHE_TTL)
                return json.dumps(payload, default=str)
            frappe.cache().set_value(cache_key, {"error": error_str}, expires_in_sec=_RETRY_CACHE_TTL)
            raise

        # ── NEW: Post-processing for AI efficiency ────────────────────────
        raw_rows = [dict(r) if isinstance(r, dict) else r for r in result.get("result", [])]
        total_count = len(raw_rows)
        report_columns = result.get("columns", [])

        # ── PREVIEW MODE: schema + count + sample ─────────────────────────
        if preview_mode:
            sample = raw_rows[:_PREVIEW_SAMPLE_ROWS]
            columnar_sample = _rows_to_columnar(sample)

            # Build column schema with types for AI understanding
            column_schema = []
            for col in report_columns:
                if isinstance(col, dict):
                    column_schema.append({
                        "fieldname": col.get("fieldname"),
                        "label": col.get("label"),
                        "fieldtype": col.get("fieldtype"),
                        "options": col.get("options"),
                        "width": col.get("width"),
                    })
                else:
                    column_schema.append({"fieldname": str(col)})

            payload = {
                "report_name": report_name,
                "report_type": report_doc.report_type,
                "preview": True,
                "total_count": total_count,
                "columns": column_schema,
                "sample_rows": columnar_sample,
                "filters_applied": effective_filters,
                "message": (
                    f"Preview: report has {total_count} total rows. "
                    f"Set preview_mode=false and use max_rows/offset to paginate. "
                    f"Use 'columns' to select specific fields and reduce token cost."
                ),
            }
            auto_added = {k: v for k, v in effective_filters.items() if k not in user_keys}
            if auto_added:
                payload["filters_auto_added"] = auto_added
            return json.dumps(payload, default=str)

        # ── COLUMN FILTERING ──────────────────────────────────────────────
        if requested_columns and raw_rows and isinstance(raw_rows[0], dict):
            # Keep only requested fields
            requested_set = set(requested_columns)
            raw_rows = [
                {k: v for k, v in row.items() if k in requested_set}
                for row in raw_rows
            ]

        # ── PAGINATION: slice then convert ────────────────────────────────
        has_more = total_count > (offset + max_rows)
        page_rows = raw_rows[offset: offset + max_rows]
        truncated = total_count > max_rows
        columnar = _rows_to_columnar(page_rows)
        fields = columnar["fields"]

        # ── AUTO-SUMMARIZE when data is truncated ─────────────────────────
        # Compute stats on ALL rows (not just the page) so the AI gets the
        # full picture. This is cheap vs. the report execution itself.
        summary = None
        if truncated or has_more:
            all_columnar = _rows_to_columnar(raw_rows)
            summary = _summarize_columns(all_columnar["rows"], all_columnar["fields"])

        # ── BUILD RESPONSE ────────────────────────────────────────────────
        payload = {
            "report_name": report_name,
            "report_type": report_doc.report_type,
            "fields": columnar["fields"],
            "rows": columnar["rows"],
            "total_count": total_count,
            "returned_count": len(page_rows),
        }

        # Pagination metadata
        if truncated or has_more or offset > 0:
            payload["pagination"] = {
                "offset": offset,
                "max_rows": max_rows,
                "has_more": has_more,
                "next_offset": offset + max_rows if has_more else None,
            }

        # Include summary when results were truncated
        if summary:
            payload["summary"] = summary

        # Column definitions (compact — only on first page or when offset=0)
        if offset == 0:
            payload["columns"] = report_columns

        payload["filters_applied"] = effective_filters
        auto_added = {k: v for k, v in effective_filters.items() if k not in user_keys}
        if auto_added:
            payload["filters_auto_added"] = auto_added

        if result.get("message"):
            payload["message"] = result["message"]

        if total_count == 0:
            payload["suggestion"] = (
                "Report returned 0 rows — auto-defaulted filters may not match your data. "
                "Retry with explicit filters or verify underlying records exist using frappe_get_list."
            )

        return json.dumps(payload, default=str)
        # ──────────────────────────────────────────────────────────────────

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to access report '{report_name}'"})
    except Exception as e:
        frappe.log_error(title="Generate Report Error", message=f"Error generating {report_name}: {str(e)}")
        frappe.cache().set_value(cache_key, {"error": str(e)}, expires_in_sec=_RETRY_CACHE_TTL)
        return json.dumps({"error": str(e), "report_name": report_name})