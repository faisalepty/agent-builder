# tools/frappe_tools/document_create.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_create_doc")
def frappe_create_doc(args: dict, **kwargs) -> str:
    """Create a new Frappe document."""
    data = args.get("doc", {})
    doctype = data.get("doctype")
    submit = args.get("submit", False)
    validate_only = args.get("validate_only", False)

    if not doctype:
        return json.dumps({"error": "doc.doctype is required"})

    if data.get("name") and frappe.db.exists(doctype, data["name"]):
        return json.dumps({
            "error": f"{doctype} '{data['name']}' already exists. Use frappe_save_doc to update it.",
            "error_type": "already_exists",
            "doctype": doctype,
            "name": data["name"],
        })

    try:
        doc = frappe.get_doc({"doctype": doctype})
        doc.check_permission("create")

        # Get DocType metadata for proper field handling
        meta = frappe.get_meta(doctype)
        table_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Table"}

        # Set field values, handling child tables explicitly
        for field, value in data.items():
            if field == "doctype":
                continue
            if field in table_fields:
                if not isinstance(value, list):
                    raise ValueError(f"Child table '{field}' requires a list, got: {type(value).__name__}")
                for row_data in value:
                    if not isinstance(row_data, dict):
                        raise ValueError(
                            f"Child table '{field}' requires list of dictionaries, got: {type(row_data).__name__}"
                        )
                    doc.append(field, row_data)
            else:
                doc.set(field, value)

        # Required-field checks are left to Frappe's own validation pipeline via
        # doc.insert()/run_method("validate") — many "reqd" fields only get populated
        # by set_missing_values() during validate(), so a pre-flight check on raw
        # input would produce false positives. MandatoryError is caught below.

        if validate_only:
            doc.run_method("validate")
            return json.dumps({
                "status": "validated",
                "doctype": doctype,
                "message": f"{doctype} data validation passed",
                "child_tables": list(table_fields.keys()),
                "next_step": "Call frappe_create_doc again with validate_only omitted to actually create it",
            })

        # Snapshot requested child-row values to compare against what's actually
        # saved, since ERPNext controllers can silently rewrite rows (rate
        # rounding, UOM conversion, currency defaults, etc.)
        input_child_values = {
            field: data[field] for field in table_fields if isinstance(data.get(field), list)
        }

        doc.insert(ignore_permissions=False)

        warnings = []
        for field, input_rows in input_child_values.items():
            saved_rows = doc.get(field) or []
            for idx, input_row in enumerate(input_rows):
                if idx >= len(saved_rows):
                    break
                saved_row = saved_rows[idx]
                for key, input_val in input_row.items():
                    saved_val = getattr(saved_row, key, None)
                    if saved_val is None or str(saved_val) == str(input_val):
                        continue
                    try:
                        if float(str(saved_val)) == float(str(input_val)):
                            continue
                    except (ValueError, TypeError):
                        pass
                    warnings.append({
                        "child_table": field,
                        "row_idx": idx,
                        "field": key,
                        "requested": input_val,
                        "saved": str(saved_val),
                    })

        result = {
            "name": doc.name,
            "doctype": doctype,
            "docstatus": doc.docstatus,
            "status": "created",
            "submitted": False,
        }

        if submit and doc.docstatus == 0:
            try:
                doc.check_permission("submit")
                doc.submit()
                result["submitted"] = True
                result["docstatus"] = 1
                result["status"] = "created_and_submitted"
            except frappe.PermissionError:
                result["submit_error"] = "No permission to submit this document; saved as draft."
            except Exception as e:
                result["submit_error"] = f"Created as draft. Submit failed: {str(e)}"

        frappe.db.commit()

        if warnings:
            result["warnings"] = warnings

        return json.dumps(result)

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to create this document"})

    except frappe.MandatoryError as e:
        # Format: "[<doctype>, <name>]: <field1>, <field2>, ..."
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
            "provided_fields": list(data.keys()),
        })

    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})

    except Exception as e:
        frappe.log_error(title="Document Create Error", message=f"Error creating {doctype}: {str(e)}")
        return json.dumps({"error": str(e), "doctype": doctype})