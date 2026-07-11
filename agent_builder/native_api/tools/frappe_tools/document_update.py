# tools/frappe_tools/document_update.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


def _apply_child_table_update(doc, field: str, child_doctype: str, rows) -> dict | None:
    """Apply patch- or replace-mode updates to a child table on `doc`.

    Mode is decided per call: if any input row has a 'name', patch mode is used
    (match by name, update matched, append unmatched, delete on '_delete': true).
    Otherwise replace mode (clear table and re-append).

    Returns None on success, or a structured error dict on failure.
    """
    if not isinstance(rows, list):
        return {
            "error": f"Child table '{field}' requires a list of dictionaries, got: {type(rows).__name__}",
            "error_type": "child_table_handling_error",
            "field": field,
        }

    for row in rows:
        if not isinstance(row, dict):
            return {
                "error": f"Child table '{field}' rows must be dictionaries, got: {type(row).__name__}",
                "error_type": "child_table_handling_error",
                "field": field,
            }

    has_named_row = any(row.get("name") for row in rows)

    if not has_named_row:
        if any(row.get("_delete") for row in rows):
            return {
                "error": f"'_delete' on child table '{field}' requires a 'name' to identify the row",
                "error_type": "child_row_not_found",
                "field": field,
            }
        doc.set(field, [])
        for row in rows:
            doc.append(field, row)
        return None

    # Patch mode: match input rows to existing rows by name.
    existing_by_name = {r.name: r for r in (doc.get(field) or []) if getattr(r, "name", None)}

    for row in rows:
        row_name = row.get("name")
        delete_marker = bool(row.get("_delete"))

        if not row_name:
            if delete_marker:
                return {
                    "error": f"'_delete' on child table '{field}' requires a 'name' to identify the row",
                    "error_type": "child_row_not_found",
                    "field": field,
                }
            doc.append(field, row)
            continue

        target = existing_by_name.get(row_name)
        if target is None:
            return {
                "error": f"Row '{row_name}' not found in {child_doctype} table '{field}'",
                "error_type": "child_row_not_found",
                "field": field,
            }

        if delete_marker:
            doc.remove(target)
            continue

        for key, value in row.items():
            if key in ("name", "_delete"):
                continue
            target.set(key, value)

    return None


def _diff_child_table_warnings(doc, field: str, input_rows: list) -> list:
    """Flag child-row values ERPNext silently overrode during save (rate
    rounding, UOM conversion, currency defaults, etc.)."""
    warnings = []
    saved_rows = doc.get(field) or []
    for idx, input_row in enumerate(input_rows):
        if idx >= len(saved_rows):
            break
        saved_row = saved_rows[idx]
        for key, input_val in input_row.items():
            if key in ("name", "_delete"):
                continue
            saved_val = getattr(saved_row, key, None)
            if saved_val is None or str(saved_val) == str(input_val):
                continue
            try:
                if float(str(saved_val)) == float(str(input_val)):
                    continue
            except (ValueError, TypeError):
                pass
            warnings.append({
                "child_table": field, "row_idx": idx, "field": key,
                "requested": input_val, "saved": str(saved_val),
            })
    return warnings


@tool(schema_name="frappe_update_doc")
def frappe_update_doc(args: dict, **kwargs) -> str:
    """Update an existing Frappe document."""
    doctype = args.get("doctype")
    name = args.get("name")
    data = args.get("data", {})

    if not doctype or not name:
        return json.dumps({"error": "Both doctype and name are required"})

    # Reject direct updates to child-table doctypes. Saving a child row in isolation
    # skips the parent's validate() pipeline, so derived fields (row amount, parent
    # grand_total, total_qty, etc.) never recompute. Caller must update the parent
    # and pass child rows through `data`.
    try:
        child_meta = frappe.get_meta(doctype)
    except Exception:
        child_meta = None

    if child_meta is not None and getattr(child_meta, "istable", 0):
        info = {
            "error": (
                f"'{doctype}' is a child-table doctype and cannot be updated directly. "
                f"Update the parent document instead and pass the child rows under the "
                f"table fieldname in `data`."
            ),
            "error_type": "child_doctype_direct_update",
            "child_doctype": doctype,
        }
        try:
            parent_name = frappe.db.get_value(doctype, name, "parent")
            parent_type = frappe.db.get_value(doctype, name, "parenttype")
            parent_field = frappe.db.get_value(doctype, name, "parentfield")
            if parent_name and parent_type and parent_field:
                info["parent_doctype"] = parent_type
                info["parent_name"] = parent_name
                info["parent_table_fieldname"] = parent_field
                info["suggestion"] = (
                    f"Call frappe_save_doc with doctype='{parent_type}', name='{parent_name}', "
                    f"data={{'{parent_field}': [{{'name': '{name}', ...fields to change...}}]}}"
                )
        except Exception:
            pass
        return json.dumps(info)

    try:
        if not frappe.db.exists(doctype, name):
            return json.dumps({"error": f"{doctype} '{name}' not found", "doctype": doctype, "name": name})

        doc = frappe.get_doc(doctype, name)
        doc.check_permission("write")

        if doc.docstatus == 2:
            return json.dumps({
                "error": f"Cannot modify cancelled document {doctype} '{name}'. Cancelled documents are read-only.",
                "docstatus": 2,
            })

        meta = frappe.get_meta(doctype)
        table_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Table"}

        for field, value in data.items():
            if field in table_fields:
                err = _apply_child_table_update(doc, field, table_fields[field], value)
                if err is not None:
                    err.update({"doctype": doctype, "name": name})
                    return json.dumps(err)
            else:
                if field in ("name", "doctype", "modified", "creation", "owner", "docstatus", "idx"):
                    continue
                df = doc.meta.get_field(field)
                if df and (df.read_only or df.hidden or df.fieldtype == "Read Only"):
                    continue
                doc.set(field, value)

        input_child_values = {f: data[f] for f in table_fields if isinstance(data.get(f), list)}

        doc.save()
        doc.reload()

        warnings = []
        for field, rows in input_child_values.items():
            warnings.extend(_diff_child_table_warnings(doc, field, rows))

        result = {
            "name": doc.name,
            "doctype": doctype,
            "status": "saved",
            "docstatus": doc.docstatus,
            "modified": str(doc.modified),
            "updated_fields": list(data.keys()),
        }
        if warnings:
            result["warnings"] = warnings

        frappe.db.commit()
        return json.dumps(result)

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to save this document"})

    except frappe.MandatoryError as e:
        error_msg = str(e)
        try:
            missing = [f.strip() for f in error_msg.partition(": ")[2].split(",") if f.strip()]
        except Exception:
            missing = []
        return json.dumps({
            "error": f"Missing required fields: {', '.join(missing)}" if missing else error_msg,
            "error_type": "missing_required_field",
            "doctype": doctype,
            "missing_fields": missing,
        })

    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})

    except Exception as e:
        frappe.log_error(title="Document Update Error", message=f"Error updating {doctype} '{name}': {str(e)}")
        return json.dumps({"error": str(e), "doctype": doctype, "name": name})