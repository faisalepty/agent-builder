# tools/frappe_tools/frappe_query.py

import json
import frappe
from frappe.query_builder import Criterion, Order
from frappe.query_builder.functions import Sum, Count, Avg, Min, Max
from frappe.desk.reportview import build_match_conditions
from agent_builder.native_api.tools.decorator import tool


ALLOWED_JOIN_TYPES = {"left", "inner"}
ALLOWED_AGG_FUNCTIONS = {"sum": Sum, "count": Count, "avg": Avg, "min": Min, "max": Max}
MAX_JOINS = 3

FILTER_OPERATORS = {
    "=": lambda f, v: f == v,
    "!=": lambda f, v: f != v,
    ">": lambda f, v: f > v,
    "<": lambda f, v: f < v,
    ">=": lambda f, v: f >= v,
    "<=": lambda f, v: f <= v,
    "in": lambda f, v: f.isin(v),
    "not_in": lambda f, v: f.notin(v),
    "like": lambda f, v: f.like(f"%{v}%"),
    "not_like": lambda f, v: f.not_like(f"%{v}%"),
    "between": lambda f, v: f.between(v[0], v[1]),
    "is_set": lambda f, v: f.isnotnull(),
    "is_not_set": lambda f, v: f.isnull(),
}

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


class QueryBuildError(Exception):
    """Raised for any invalid operation, doctype, field, or permission failure."""
    pass


@tool(schema_name="frappe_query")
def frappe_query(args: dict, **kwargs) -> str:
    """Run a read-only multi-step query across linked doctypes, with optional
    filtering, joins, and grouping/aggregation, using Frappe's native query builder."""
    operations = args.get("operations")

    if not operations or not isinstance(operations, list):
        return json.dumps({"error": "operations must be a non-empty list"})

    try:
        builder = _QueryContext()
        for idx, op in enumerate(operations):
            op = op or {}
            op_type = op.get("type")
            handler = builder.HANDLERS.get(op_type)

            if handler is None:
                raise QueryBuildError(
                    f"Operation {idx + 1}: unsupported type '{op_type}'. "
                    f"Allowed types: {sorted(builder.HANDLERS)}"
                )

            handler(builder, op)

        rows = builder.execute()

        return json.dumps({
            "data": rows,
            "count": len(rows),
            "doctypes_used": builder.doctypes_used,
            "warnings": builder.warnings,
        }, default=str)

    except QueryBuildError as e:
        return json.dumps({"error": str(e), "error_type": "invalid_query"})
    except frappe.PermissionError as e:
        return json.dumps({"error": str(e), "error_type": "permission_denied"})
    except Exception as e:
        frappe.log_error(title="Frappe Query Tool Error", message=f"{str(e)}\nOperations: {json.dumps(operations, default=str)}")
        return json.dumps({"error": str(e)})


class _QueryContext:
    """Walks the operations list in order and incrementally builds a
    frappe.query_builder query, mirroring a linear pipeline (not a DAG)."""

    STANDARD_FIELDS = frozenset({
        "name", "creation", "modified", "owner", "modified_by", "docstatus",
        "parent", "parenttype", "parentfield", "idx",
    })

    def __init__(self):
        self.query = None
        self.source_dt = None
        self.source_tbl = None
        self.tables = {}          # doctype -> qb table object
        self.metas = {}           # doctype -> frappe Meta (cached, avoids repeat lookups)
        self.doctypes_used = []
        self.join_count = 0
        self.group_by_fields = []
        self.has_summarize = False
        self.limit_value = DEFAULT_LIMIT
        self.warnings = []

    # ---- helpers -----------------------------------------------------

    def _get_meta(self, doctype):
        if doctype not in self.metas:
            if not frappe.db.exists("DocType", doctype):
                raise QueryBuildError(f"Doctype '{doctype}' does not exist")
            self.metas[doctype] = frappe.get_meta(doctype)
        return self.metas[doctype]

    def _check_field(self, doctype, fieldname):
        if fieldname in self.STANDARD_FIELDS:
            return
        if not self._get_meta(doctype).has_field(fieldname):
            raise QueryBuildError(f"Field '{fieldname}' does not exist on doctype '{doctype}'")

    def _get_table(self, doctype):
        if doctype not in self.tables:
            self._get_meta(doctype)  # existence check
            if not frappe.has_permission(doctype, ptype="read"):
                raise frappe.PermissionError(f"No permission to read '{doctype}'")
            self.tables[doctype] = frappe.qb.DocType(doctype)
            self.doctypes_used.append(doctype)
        return self.tables[doctype]

    def _row_permission_condition(self, doctype):
        """User-permission / permission-query-condition restrictions Frappe normally
        applies automatically in get_list — frappe.qb bypasses these, so they're
        added back in manually per doctype touched."""
        match_conditions = build_match_conditions(doctype)
        if match_conditions:
            return frappe.qb.raw(match_conditions)
        return None

    def _resolve_field(self, field_spec):
        """field_spec is either 'fieldname' (resolves against source doctype)
        or 'Doctype.fieldname' (resolves against a joined doctype)."""
        if "." in field_spec:
            doctype, fieldname = field_spec.split(".", 1)
            if doctype not in self.tables:
                raise QueryBuildError(f"'{doctype}' has not been joined yet, cannot reference '{field_spec}'")
        else:
            doctype, fieldname = self.source_dt, field_spec
        self._check_field(doctype, fieldname)
        return getattr(self.tables[doctype], fieldname)

    def _build_condition(self, filter_op):
        field_spec = filter_op.get("field")
        operator = filter_op.get("operator")
        value = filter_op.get("value")

        if not field_spec or operator not in FILTER_OPERATORS:
            raise QueryBuildError(
                f"Filter requires 'field' and a valid 'operator'. Allowed operators: {sorted(FILTER_OPERATORS)}"
            )

        field = self._resolve_field(field_spec)
        return FILTER_OPERATORS[operator](field, value)

    # ---- operation handlers -------------------------------------------

    def _apply_source(self, op):
        if self.query is not None:
            raise QueryBuildError("'source' must be the first operation")
        doctype = op.get("doctype")
        if not doctype:
            raise QueryBuildError("'source' requires 'doctype'")
        meta = self._get_meta(doctype)

        if getattr(meta, "istable", 0):
            self._setup_child_source(doctype)
            return

        self.source_dt = doctype
        self.source_tbl = self._get_table(doctype)
        self.query = frappe.qb.from_(self.source_tbl)
        row_condition = self._row_permission_condition(doctype)
        if row_condition is not None:
            self.query = self.query.where(row_condition)

    def _setup_child_source(self, doctype):
        """Child tables have no permission model of their own — access is entirely
        inherited from whichever parent doctype(s) embed them. Resolve the parent(s)
        automatically (no input needed from the model), check read permission on
        each, and scope returned rows to only those belonging to a parent record
        the user can actually read."""
        parent_doctypes = frappe.get_all(
            "DocField",
            filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]], "options": doctype},
            pluck="parent",
            distinct=True,
        )
        if not parent_doctypes:
            raise QueryBuildError(
                f"'{doctype}' is a child table with no doctype referencing it as a Table field — "
                f"can't determine read permissions for it."
            )

        for parent_dt in parent_doctypes:
            if not frappe.has_permission(parent_dt, ptype="read"):
                raise frappe.PermissionError(
                    f"'{doctype}' rows belong to '{parent_dt}' records, which you don't have "
                    f"permission to read."
                )

        self.source_dt = doctype
        self.source_tbl = frappe.qb.DocType(doctype)
        self.tables[doctype] = self.source_tbl
        self.doctypes_used.append(doctype)
        self.query = frappe.qb.from_(self.source_tbl)
        allowed_subqueries = []
        for parent_dt in parent_doctypes:
            parent_tbl = frappe.qb.DocType(parent_dt)
            sub = frappe.qb.from_(parent_tbl).select(parent_tbl.name)
            row_condition = self._row_permission_condition(parent_dt)
            if row_condition is not None:
                sub = sub.where(row_condition)
            allowed_subqueries.append(sub)

        if len(allowed_subqueries) == 1:
            self.query = self.query.where(self.source_tbl.parent.isin(allowed_subqueries[0]))
        else:
            # shared child table — a row is visible if its parent is permitted
            # under ANY of the doctypes that use this child table
            self.query = self.query.where(
                Criterion.any(self.source_tbl.parent.isin(sub) for sub in allowed_subqueries)
            )

    def _require_source(self):
        if self.query is None:
            raise QueryBuildError("'source' must be the first operation")

    def _apply_filter(self, op):
        self._require_source()
        self.query = self.query.where(self._build_condition(op))

    def _apply_filter_group(self, op):
        self._require_source()
        logic = op.get("logic", "and")
        filters = op.get("filters") or []
        if not filters:
            raise QueryBuildError("'filter_group' requires a non-empty 'filters' list")

        conditions = [self._build_condition(f) for f in filters]
        if logic == "and":
            combined = Criterion.all(conditions)
        elif logic == "or":
            combined = Criterion.any(conditions)
        else:
            raise QueryBuildError("'filter_group' logic must be 'and' or 'or'")

        self.query = self.query.where(combined)

    def _apply_join(self, op):
        self._require_source()
        doctype = op.get("doctype")
        join_type = op.get("join_type", "left")
        left_field = op.get("left_field")
        right_field = op.get("right_field")
        select_fields = op.get("select") or []

        if not doctype or not left_field or not right_field:
            raise QueryBuildError("'join' requires 'doctype', 'left_field', and 'right_field'")
        if join_type not in ALLOWED_JOIN_TYPES:
            raise QueryBuildError(f"join_type must be one of {sorted(ALLOWED_JOIN_TYPES)}")
        if doctype in self.tables:
            raise QueryBuildError(f"'{doctype}' has already been joined — joining the same doctype twice isn't supported")
        if self.join_count >= MAX_JOINS:
            raise QueryBuildError(f"A single query supports at most {MAX_JOINS} joins")

        self._check_field(self.source_dt, left_field)
        self._check_field(doctype, right_field)
        self._warn_if_not_a_real_link(doctype, left_field, right_field)

        right_tbl = self._get_table(doctype)  # existence/permission-checked here
        self.join_count += 1

        left_col = getattr(self.source_tbl, left_field)
        right_col = getattr(right_tbl, right_field)
        condition = left_col == right_col

        if join_type == "left":
            self.query = self.query.left_join(right_tbl).on(condition)
        else:
            self.query = self.query.inner_join(right_tbl).on(condition)

        row_condition = self._row_permission_condition(doctype)
        if row_condition is not None:
            self.query = self.query.where(row_condition)

        for f in select_fields:
            self._check_field(doctype, f)
            self.query = self.query.select(getattr(right_tbl, f).as_(f"{doctype}.{f}"))

    def _warn_if_not_a_real_link(self, doctype, left_field, right_field):
        """left_field/right_field existing doesn't mean they're actually related —
        flag joins that don't look like a real Link relationship so a nonsensical
        join produces a visible warning instead of a silent empty/garbage result."""
        source_meta = self._get_meta(self.source_dt)
        field_def = source_meta.get_field(left_field)
        if field_def is not None and field_def.fieldtype == "Link":
            if field_def.options != doctype:
                self.warnings.append(
                    f"'{self.source_dt}.{left_field}' is a Link to '{field_def.options}', not "
                    f"'{doctype}' — this join may not return meaningful matches."
                )
        elif right_field != "name":
            self.warnings.append(
                f"'{self.source_dt}.{left_field}' doesn't appear to be a Link field to '{doctype}' — "
                f"double-check this join is between actually related records."
            )

    def _apply_select(self, op):
        self._require_source()
        fields = op.get("fields") or []
        if not fields:
            raise QueryBuildError("'select' requires a non-empty 'fields' list")
        for f in fields:
            self.query = self.query.select(self._resolve_field(f))

    def _apply_summarize(self, op):
        self._require_source()
        self.has_summarize = True
        group_by = op.get("group_by") or []
        measures = op.get("measures") or []

        if not group_by and not measures:
            raise QueryBuildError("'summarize' requires 'group_by' and/or 'measures'")

        for f in group_by:
            field = self._resolve_field(f)
            self.query = self.query.select(field).groupby(field)
            self.group_by_fields.append(f)

        for m in measures:
            field_spec = m.get("field")
            fn_name = m.get("function")
            alias = m.get("as") or f"{fn_name}_{field_spec}"

            if fn_name not in ALLOWED_AGG_FUNCTIONS:
                raise QueryBuildError(f"Aggregate function must be one of {sorted(ALLOWED_AGG_FUNCTIONS)}")

            field = self._resolve_field(field_spec)
            agg_fn = ALLOWED_AGG_FUNCTIONS[fn_name]
            self.query = self.query.select(agg_fn(field).as_(alias))

    def _apply_order_by(self, op):
        self._require_source()
        field_spec = op.get("field")
        direction = op.get("direction", "asc")
        if not field_spec:
            raise QueryBuildError("'order_by' requires 'field'")

        # aggregated columns (aliases from summarize) aren't resolvable via
        # _resolve_field, so fall back to ordering by raw alias name in that case
        try:
            field = self._resolve_field(field_spec)
        except QueryBuildError:
            if self.has_summarize:
                field = field_spec
            else:
                raise

        order = Order.asc if direction == "asc" else Order.desc
        self.query = self.query.orderby(field, order=order)

    def _apply_limit(self, op):
        self._require_source()
        value = op.get("value", DEFAULT_LIMIT)
        if not isinstance(value, int) or value < 1:
            raise QueryBuildError("'limit' value must be a positive integer")
        self.limit_value = min(value, MAX_LIMIT)

    # ---- execution ------------------------------------------------------

    def execute(self):
        self._require_source()
        self.query = self.query.limit(self.limit_value)
        result = self.query.run(as_dict=True)
        return result

    HANDLERS = {
        "source": _apply_source,
        "filter": _apply_filter,
        "filter_group": _apply_filter_group,
        "join": _apply_join,
        "select": _apply_select,
        "summarize": _apply_summarize,
        "order_by": _apply_order_by,
        "limit": _apply_limit,
    }
