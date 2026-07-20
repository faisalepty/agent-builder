# tools/frappe_tools/frappe_query.py

import json
import frappe
from frappe.query_builder import Criterion, Order
from frappe.query_builder.functions import Sum, Count, Avg, Min, Max
from agent_builder.native_api.tools.decorator import tool


ALLOWED_OP_TYPES = {"source", "filter", "filter_group", "join", "select", "summarize", "order_by", "limit"}
ALLOWED_JOIN_TYPES = {"left", "inner"}
ALLOWED_AGG_FUNCTIONS = {"sum": Sum, "count": Count, "avg": Avg, "min": Min, "max": Max}

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
    "between": lambda f, v: f[v[0]:v[1]],
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
    """Run a read-only multi-step query across one or two linked doctypes,
    with optional grouping and aggregation, using Frappe's native query builder."""
    operations = args.get("operations")

    if not operations or not isinstance(operations, list):
        return json.dumps({"error": "operations must be a non-empty list"})

    try:
        builder = _QueryContext()
        for idx, op in enumerate(operations):
            op = op or {}
            op_type = op.get("type")

            if op_type not in ALLOWED_OP_TYPES:
                raise QueryBuildError(
                    f"Operation {idx + 1}: unsupported type '{op_type}'. "
                    f"Allowed types: {sorted(ALLOWED_OP_TYPES)}"
                )

            handler = getattr(builder, f"_apply_{op_type}")
            handler(op)

        rows = builder.execute()

        return json.dumps({
            "data": rows,
            "count": len(rows),
            "doctypes_used": builder.doctypes_used,
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

    def __init__(self):
        self.query = None
        self.source_dt = None
        self.source_tbl = None
        self.tables = {}          # doctype -> qb table object
        self.doctypes_used = []
        self.group_by_fields = []
        self.has_summarize = False
        self.select_fields = None  # explicit select() list, if given
        self.limit_value = DEFAULT_LIMIT

    # ---- helpers -----------------------------------------------------

    def _check_doctype(self, doctype):
        if not frappe.db.exists("DocType", doctype):
            raise QueryBuildError(f"Doctype '{doctype}' does not exist")
        if not frappe.has_permission(doctype, ptype="read"):
            raise frappe.PermissionError(f"No permission to read '{doctype}'")

    def _check_field(self, doctype, fieldname):
        if fieldname in ("name", "creation", "modified", "owner", "modified_by", "docstatus"):
            return
        meta = frappe.get_meta(doctype)
        if not meta.has_field(fieldname):
            raise QueryBuildError(f"Field '{fieldname}' does not exist on doctype '{doctype}'")

    def _get_table(self, doctype):
        if doctype not in self.tables:
            self._check_doctype(doctype)
            self.tables[doctype] = frappe.qb.DocType(doctype)
            self.doctypes_used.append(doctype)
        return self.tables[doctype]

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
        self.source_dt = doctype
        self.source_tbl = self._get_table(doctype)
        self.query = frappe.qb.from_(self.source_tbl)

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

        right_tbl = self._get_table(doctype)
        self._check_field(self.source_dt, left_field)
        self._check_field(doctype, right_field)

        left_col = getattr(self.source_tbl, left_field)
        right_col = getattr(right_tbl, right_field)
        condition = left_col == right_col

        if join_type == "left":
            self.query = self.query.left_join(right_tbl).on(condition)
        else:
            self.query = self.query.inner_join(right_tbl).on(condition)

        for f in select_fields:
            self._check_field(doctype, f)
            self.query = self.query.select(getattr(right_tbl, f).as_(f"{doctype}.{f}"))

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

