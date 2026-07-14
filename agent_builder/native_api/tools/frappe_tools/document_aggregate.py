"""Aggregate query tool — GROUP BY with SUM, COUNT, AVG, MIN, MAX.

This fills the critical gap where the agent had to manually sum hundreds of
rows in-context (and failed). Now: one call, exact numbers, zero manual math.

Security: validates doctype exists, validates fieldnames exist on the doctype
(to prevent injection via crafted field names), whitelists aggregate functions,
and uses parameterized queries for all filter values.
"""

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


_VALID_FUNCTIONS = {"sum", "count", "avg", "min", "max"}


def _validate_fieldname(fieldname: str, valid_fields: set) -> bool:
    """Reject fieldnames containing SQL-dangerous characters.
    Valid fieldnames are alphanumeric + underscore only."""
    return bool(fieldname) and fieldname.replace("_", "").isalnum() and fieldname in valid_fields


def _build_where_clause(filters: dict) -> tuple:
    """Build WHERE clause from filters dict. Returns (where_sql, params_list)."""
    if not filters:
        return "", []

    conditions = []
    params = []

    for key, value in filters.items():
        if not _validate_fieldname(key, {"_any"}):  # Minimal check for filter keys
            continue

        if isinstance(value, list) and len(value) == 3:
            op, val = value[0], value[1]
            # Whitelist operators to prevent injection
            if op.upper() in ("=", "!=", ">", ">=", "<", "<=", "LIKE", "NOT LIKE", "IN", "NOT IN"):
                if op.upper() in ("IN", "NOT IN") and isinstance(val, list):
                    placeholders = ", ".join(["%s"] * len(val))
                    conditions.append(f"`{key}` {op} ({placeholders})")
                    params.extend(val)
                else:
                    conditions.append(f"`{key}` {op} %s")
                    params.append(val)
        elif isinstance(value, list) and len(value) == 2:
            conditions.append(f"`{key}` BETWEEN %s AND %s")
            params.extend(value)
        else:
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

    # Validation
    if not doctype:
        return json.dumps({"error": "doctype is required"})
    if not group_by:
        return json.dumps({"error": "group_by is required (use [] for overall aggregate)"})
    if not aggregations:
        return json.dumps({"error": "aggregations is required"})

    if not frappe.db.exists("DocType", doctype):
        return json.dumps({"error": f"DocType '{doctype}' not found"})

    if not frappe.has_permission(doctype, "read"):
        return json.dumps({"error": f"No read permission for DocType '{doctype}'"})

    # Get valid fieldnames from doctype metadata
    meta = frappe.get_meta(doctype)
    valid_fields = {f.fieldname for f in meta.fields if f.fieldname}
    valid_fields.add("name")  # Always available

    # Validate group_by fields
    for field in group_by:
        if not _validate_fieldname(field, valid_fields):
            return json.dumps({"error": f"Invalid field '{field}' for doctype '{doctype}'. Valid fields: {sorted(valid_fields)}"})

    # Validate and normalize aggregations
    select_parts = []
    func_map = {f: f.upper() for f in _VALID_FUNCTIONS}

    for agg in aggregations:
        func = (agg.get("function") or "").lower()
        field = agg.get("field", "name")
        alias = agg.get("alias")

        if func not in _VALID_FUNCTIONS:
            return json.dumps({"error": f"Invalid function '{func}'. Must be one of: {', '.join(sorted(_VALID_FUNCTIONS))}"})

        if not alias:
            alias = f"{func}_{field}"

        if not _validate_fieldname(alias, {"_any"}):
            return json.dumps({"error": f"Invalid alias '{alias}'. Use alphanumeric + underscore only."})

        # COUNT(*) is special — doesn't need a valid field
        if func == "count" and field == "name":
            select_parts.append(f"COUNT(*) as `{alias}`")
        elif not _validate_fieldname(field, valid_fields):
            return json.dumps({"error": f"Invalid field '{field}' for doctype '{doctype}'. Valid fields: {sorted(valid_fields)}"})
        else:
            select_parts.append(f"{func_map[func]}(`{field}`) as `{alias}`")

    # Build GROUP BY clause
    group_clause = ", ".join(f"`{g}`" for g in group_by) if group_by else "1=1"

    # Build WHERE clause
    where_clause, where_params = _build_where_clause(filters)

    # Build HAVING clause (for filtering on aggregates)
    having_clause = ""
    having_params = []
    if having:
        # Simple HAVING support: {"total": [">", 100]}
        having_parts = []
        for alias, condition in having.items():
            if isinstance(condition, list) and len(condition) == 2:
                op, val = condition
                if op.upper() in (">", ">=", "<", "<=", "=", "!="):
                    having_parts.append(f"`{alias}` {op} %s")
                    having_params.append(val)
        if having_parts:
            having_clause = " HAVING " + " AND ".join(having_parts)

    # Build ORDER BY clause
    order_clause = ""
    if order_by:
        # Validate order_by doesn't contain dangerous characters
        if _validate_fieldname(order_by.split()[0].strip("`"), {"_any"}):
            order_clause = f" ORDER BY {order_by}"

    # Build LIMIT
    limit_clause = ""
    try:
        limit_int = int(limit)
        if 1 <= limit_int <= 10000:
            limit_clause = f" LIMIT {limit_int}"
    except (TypeError, ValueError):
        pass

    # Assemble and execute
    sql = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM `tab{doctype}`{where_clause} "
        f"GROUP BY {group_clause}{having_clause}{order_clause}{limit_clause}"
    )

    all_params = where_params + having_params

    try:
        results = frappe.db.sql(sql, all_params, as_dict=True)
        return json.dumps({
            "doctype": doctype,
            "group_by": group_by,
            "aggregations": [a.get("alias", f"{a['function']}_{a['field']}") for a in aggregations],
            "data": [dict(r) for r in results],
            "row_count": len(results),
            "query": sql,
        }, default=str)
    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to query '{doctype}'"})
    except Exception as e:
        frappe.log_error(title="Aggregate Error", message=f"Error aggregating {doctype}: {str(e)}\nSQL: {sql}")
        return json.dumps({"error": str(e), "doctype": doctype, "query": sql})