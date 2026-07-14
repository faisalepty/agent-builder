"""Aggregate query tool — GROUP BY with SUM, COUNT, AVG, MIN, MAX.

This fills the critical gap where the agent had to manually sum hundreds of
rows in-context (and failed). Now: one call, exact numbers, zero manual math.

Security: validates doctype exists, validates GROUP BY fieldnames exist on
the doctype (to prevent injection via crafted field names), validates
aggregate fieldnames exist, whitelists aggregate functions, and uses
parameterized queries for all filter values. Aliases only need to be safe
SQL identifiers — they are NOT checked against doctype fields because they
are user-defined output column names.
"""

import json
import re
import frappe
from agent_builder.native_api.tools.decorator import tool


_VALID_FUNCTIONS = {"sum", "count", "avg", "min", "max"}

# Regex for a safe SQL identifier: starts with letter/underscore, followed by
# letters, digits, or underscores. Rejects anything with spaces, hyphens,
# dots, or SQL-dangerous characters.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Operators that indicate a filter is using [op, value] syntax rather than
# a BETWEEN range [start, end].
_OPERATOR_OPS = {
    "=", "!=", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IN", "NOT IN",
}


def _is_safe_identifier(name: str) -> bool:
    """Check if a string is a safe SQL identifier (for aliases, order_by)."""
    return bool(name) and bool(_SAFE_IDENTIFIER_RE.match(name))


def _is_valid_fieldname(fieldname: str, valid_fields: set) -> bool:
    """Check if a fieldname is safe AND exists on the doctype."""
    return bool(fieldname) and _is_safe_identifier(fieldname) and fieldname in valid_fields


def _build_where_clause(filters: dict) -> tuple:
    """Build WHERE clause from filters dict. Returns (where_sql, params_list).

    Supported filter formats:
      - {"field": "value"}                       → field = %s
      - {"field": [">=", "value"]}                → field >= %s  (operator syntax)
      - {"field": ["IN", ["a", "b"]]}             → field IN (%s, %s)
      - {"field": ["start", "end"]}               → field BETWEEN %s AND %s
      - {"field": [">", "value", "extra_ignored"]}→ field > %s (3rd elem ignored for compat)

    Disambiguation: a 2-element list is treated as BETWEEN *only* when the
    first element is NOT a recognised operator. This prevents [">=", "2026-01-01"]
    from being silently mangled into a broken BETWEEN clause.
    """
    if not filters:
        return "", []

    conditions = []
    params = []

    for key, value in filters.items():
        if not _is_safe_identifier(key):
            continue

        if isinstance(value, list) and len(value) >= 3:
            # 3+ elements: first is operator, second is value
            op, val = value[0], value[1]
            if isinstance(op, str) and op.upper() in _OPERATOR_OPS:
                op = op.upper()
                if op in ("IN", "NOT IN") and isinstance(val, list):
                    if not val:
                        continue
                    placeholders = ", ".join(["%s"] * len(val))
                    conditions.append(f"`{key}` {op} ({placeholders})")
                    params.extend(val)
                else:
                    conditions.append(f"`{key}` {op} %s")
                    params.append(val)
                continue

        if isinstance(value, list) and len(value) == 2:
            # 2-element list: disambiguate operator syntax from BETWEEN range
            first = value[0]
            if isinstance(first, str) and first.upper() in _OPERATOR_OPS:
                # Operator syntax: [">=", "2026-01-01"]
                op = first.upper()
                conditions.append(f"`{key}` {op} %s")
                params.append(value[1])
            else:
                # BETWEEN range: ["2026-01-01", "2026-12-31"]
                conditions.append(f"`{key}` BETWEEN %s AND %s")
                params.extend(value)
            continue

        if isinstance(value, list):
            # Single-element list or empty — treat as plain value
            if value:
                conditions.append(f"`{key}` = %s")
                params.append(value[0])
            continue

        # Scalar value
        conditions.append(f"`{key}` = %s")
        params.append(value)

    if not conditions:
        return "", []

    return " WHERE " + " AND ".join(conditions), params


@tool(schema_name="frappe_aggregate")
def frappe_aggregate(args: dict = None, **kwargs) -> str:
    """Run a GROUP BY aggregate query on a doctype — SUM, COUNT, AVG, MIN, MAX.

    Use this for any analytical question: 'total sales per customer', 'downtime
    hours per machine', 'count of orders by status'. Do NOT fetch raw rows
    with frappe_get_list and try to sum them manually.
    """
    args = args or kwargs
    doctype = args.get("doctype")
    group_by = args.get("group_by", [])
    aggregations = args.get("aggregations", [])
    filters = args.get("filters", {})
    order_by = args.get("order_by")
    limit = args.get("limit", 100)
    having = args.get("having")

    # ── Validation ───────────────────────────────────────────────────

    if not doctype:
        return json.dumps({"error": "doctype is required"})

    if not frappe.db.exists("DocType", doctype):
        return json.dumps({"error": f"DocType '{doctype}' not found"})

    if not frappe.has_permission(doctype, "read"):
        return json.dumps({"error": f"No read permission for DocType '{doctype}'"})

    # Get valid fieldnames from doctype metadata
    meta = frappe.get_meta(doctype)
    valid_fields = {f.fieldname for f in meta.fields if f.fieldname}
    valid_fields.add("name")  # Always available

    # Validate group_by fields — must be real doctype fields
    for field in group_by:
        if not _is_valid_fieldname(field, valid_fields):
            return json.dumps({
                "error": f"Invalid group_by field '{field}' for doctype '{doctype}'. "
                       f"Valid fields include: {sorted(valid_fields)}",
            })

    # Validate and normalize aggregations
    select_parts = []
    func_map = {f: f.upper() for f in _VALID_FUNCTIONS}

    for agg in aggregations:
        func = (agg.get("function") or "").lower()
        field = agg.get("field", "name")
        alias = agg.get("alias")

        if func not in _VALID_FUNCTIONS:
            return json.dumps({
                "error": f"Invalid function '{func}'. "
                       f"Must be one of: {', '.join(sorted(_VALID_FUNCTIONS))}",
            })

        if not alias:
            alias = f"{func}_{field}"

        # Alias just needs to be a safe SQL identifier, NOT a doctype field
        if not _is_safe_identifier(alias):
            return json.dumps({
                "error": f"Invalid alias '{alias}'. "
                       f"Use only letters, digits, and underscores (no spaces or special characters).",
            })

        # The field being aggregated MUST be a real doctype field
        if func == "count" and field == "name":
            select_parts.append(f"COUNT(*) as `{alias}`")
        elif not _is_valid_fieldname(field, valid_fields):
            return json.dumps({
                "error": f"Invalid field '{field}' for doctype '{doctype}'. "
                       f"Valid fields include: {sorted(valid_fields)}",
            })
        else:
            select_parts.append(f"{func_map[func]}(`{field}`) as `{alias}`")

    # ── Build query ───────────────────────────────────────────────────

    # SELECT: group_by fields FIRST (so labels appear in every result row),
    # then aggregate expressions.
    final_select_parts = []
    if group_by:
        for g in group_by:
            final_select_parts.append(f"`{g}`")
    final_select_parts.extend(select_parts)

    # GROUP BY
    if group_by:
        group_clause = ", ".join(f"`{g}`" for g in group_by)
    else:
        group_clause = "1=1"

    # WHERE
    where_clause, where_params = _build_where_clause(filters)

    # HAVING — filter on aggregate results
    having_clause = ""
    having_params = []
    if having:
        _HAVING_OPS = {">", ">=", "<", "<=", "=", "!="}
        having_parts = []
        for alias, condition in having.items():
            if not _is_safe_identifier(alias):
                continue
            if isinstance(condition, list) and len(condition) == 2:
                op, val = condition
                if op in _HAVING_OPS:
                    having_parts.append(f"`{alias}` {op} %s")
                    having_params.append(val)
        if having_parts:
            having_clause = " HAVING " + " AND ".join(having_parts)

    # ORDER BY — can reference group_by fields or aliases
    order_clause = ""
    if order_by and _is_safe_identifier(order_by.split()[0].strip("`")):
        # Allow desc/asc suffix
        order_clause = f" ORDER BY {order_by}"

    # LIMIT
    limit_clause = ""
    try:
        limit_int = int(limit)
        if 1 <= limit_int <= 10000:
            limit_clause = f" LIMIT {limit_int}"
    except (TypeError, ValueError):
        pass

    # ── Execute ──────────────────────────────────────────────────────

    sql = (
        f"SELECT {', '.join(final_select_parts)} "
        f"FROM `tab{doctype}`{where_clause} "
        f"GROUP BY {group_clause}{having_clause}{order_clause}{limit_clause}"
    )

    all_params = where_params + having_params

    try:
        results = frappe.db.sql(sql, all_params, as_dict=True)
        return json.dumps({
            "doctype": doctype,
            "group_by": group_by,
            "aggregations": [
                a.get("alias", f"{a['function']}_{a['field']}")
                for a in aggregations
            ],
            "data": [dict(r) for r in results],
            "row_count": len(results),
            "query": sql,
        }, default=str)
    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to query '{doctype}'"})
    except Exception as e:
        frappe.log_error(
            title="Aggregate Error",
            message=f"Error aggregating {doctype}: {str(e)}\nSQL: {sql}",
        )
        return json.dumps({"error": str(e), "doctype": doctype, "query": sql})


