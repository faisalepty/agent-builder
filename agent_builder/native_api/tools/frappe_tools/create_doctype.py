import frappe
from typing import Dict, Any
from agent_builder.native_api.tools.decorator import tool

@tool(schema_name="create_document")
def create_document(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new document"""
    doctype = arguments.get("doctype")
    data = arguments.get("data", {})
    submit = arguments.get("submit", False)
    validate_only = arguments.get("validate_only", False)

    try:
        # 1. Native Frappe Doctype-Level Permission Check
        if not frappe.has_permission(doctype, "create"):
            return {
                "success": False,
                "error": f"Insufficient permissions to create {doctype} documents."
            }

        meta = frappe.get_meta(doctype)
        
        # 2. Native System & Sensitive Field Filtering
        # Prevent the agent from manipulating core system fields natively
        system_fields = {"owner", "creation", "modified", "modified_by", "docstatus", "idx", "name"}
        # Prevent manipulating password fields natively
        sensitive_fieldtypes = {"Password"}
        
        restricted_fields_attempted = []
        for field in data.keys():
            if field in system_fields:
                restricted_fields_attempted.append(field)
                continue
                
            df = meta.get_field(field)
            if df and df.fieldtype in sensitive_fieldtypes:
                restricted_fields_attempted.append(field)

        if restricted_fields_attempted:
            return {
                "success": False,
                "error": f"Cannot set system or restricted fields: {', '.join(restricted_fields_attempted)}.",
            }

        # 3. Native Submit Permission Check
        if submit:
            if not frappe.has_permission(doctype, "submit"):
                # Rather than failing, gracefully degrade to Draft if they lack submit rights
                submit = False
                submit_warning = True
            else:
                submit_warning = False

        # Create document
        doc = frappe.new_doc(doctype)
        table_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Table"}

        # Set field values with proper child table handling
        for field, value in data.items():
            if field in table_fields:
                if isinstance(value, list):
                    for row_data in value:
                        if isinstance(row_data, dict):
                            doc.append(field, row_data)
                        else:
                            raise ValueError(
                                f"Child table '{field}' requires list of dictionaries, got: {type(row_data)}"
                            )
                else:
                    raise ValueError(f"Child table '{field}' requires a list, got: {type(value)}")
            else:
                setattr(doc, field, value)

        # Handle validation-only mode
        if validate_only:
            doc.run_method("validate")
            return {
                "success": True,
                "validation_passed": True,
                "doctype": doctype,
                "message": f"{doctype} data validation passed successfully",
                "fields_validated": list(data.keys()),
                "child_tables": list(table_fields.keys()) if table_fields else [],
                "next_step": "Use create_document with validate_only=false to actually create the document",
            }

        # Capture input child-table values for post-save comparison
        input_child_values = {}
        for field, value in data.items():
            if field in table_fields and isinstance(value, list):
                input_child_values[field] = value

        # Save document - ignore_permissions=False ensures native Field Level Permissions are respected
        doc.insert(ignore_permissions=False)
        
        # Check for silently overridden field values
        warnings = []
        for field, input_rows in input_child_values.items():
            saved_rows = doc.get(field) or []
            for idx, input_row in enumerate(input_rows):
                if idx >= len(saved_rows):
                    break
                saved_row = saved_rows[idx]
                for key, input_val in input_row.items():
                    saved_val = getattr(saved_row, key, None)
                    if saved_val is not None and str(saved_val) != str(input_val):
                        try:
                            if float(str(saved_val)) == float(str(input_val)):
                                continue
                        except (ValueError, TypeError):
                            pass
                        warnings.append(
                            {
                                "child_table": field,
                                "row_idx": idx,
                                "field": key,
                                "requested": input_val,
                                "saved": str(saved_val),
                                "reason": "Value was overridden by Frappe validation logic",
                            }
                        )
                        
        if submit and submit_warning:
             warnings.append({"message": f"Your role does not have submit permission for {doctype}. Saved as draft."})

        # Initialize result with basic information
        result = {
            "success": True,
            "name": doc.name,
            "doctype": doctype,
            "docstatus": doc.docstatus,
            "owner": doc.owner,
            "creation": str(doc.creation),
            "submitted": False,
            "can_submit": frappe.has_permission(doctype, "submit", doc=doc.name),
        }

        # Submit if requested and allowed
        if submit and doc.docstatus == 0:
            try:
                doc.submit()
                result["submitted"] = True
                result["docstatus"] = 1
                result["message"] = f"{doctype} '{doc.name}' created and submitted successfully"
            except Exception as e:
                result["message"] = f"{doctype} '{doc.name}' created as draft. Submit failed: {str(e)}"
                result["submit_error"] = str(e)
        else:
            result["message"] = f"{doctype} '{doc.name}' created successfully as draft"

        if hasattr(doc, "workflow_state") and doc.workflow_state:
            result["workflow_state"] = doc.workflow_state

        if doc.docstatus == 0:
            result["next_steps"] = [
                "Document is in draft state",
                "You can update this document using document_update tool",
                f"Submit permission: {'Available' if result['can_submit'] else 'Not available'}",
            ]
        else:
            result["next_steps"] = [
                "Document is submitted and cannot be modified",
                "Use document_get to view the submitted document",
            ]

        if warnings:
            result["warnings"] = warnings

        return result

    except frappe.MandatoryError as e:
        error_msg = str(e)
        try:
            fields_part = error_msg.partition(": ")[2]
            missing = [f.strip() for f in fields_part.split(",") if f.strip()]
        except Exception:
            missing = []

        return {
            "success": False,
            "error": (
                f"Missing required fields: {', '.join(missing)}"
                if missing
                else f"Missing required fields. Raw error: {error_msg}"
            ),
            "error_type": "missing_required_field",
            "doctype": doctype,
            "missing_fields": missing,
            "provided_fields": list(data.keys()),
            "suggestion": (
                f"Use get_doctype_info tool with doctype='{doctype}' to see all required "
                f"fields and supply values for: {', '.join(missing)}."
                if missing
                else f"Use get_doctype_info tool with doctype='{doctype}' to see all required fields."
            ),
        }
    except Exception as e:
        frappe.log_error(title="Document Creation Error", message=f"Error creating {doctype}: {str(e)}")
        error_msg = str(e)
        result = {"success": False, "error": error_msg, "doctype": doctype}

        if "'dict' object has no attribute 'is_new'" in error_msg:
            result.update({
                "error_type": "child_table_handling_error",
                "guidance": "Child table data is not properly formatted. They require lists of dictionaries.",
                "suggestion": f"Example: {{'items': [{{'item_code': 'ITEM001', 'qty': 10}}]}}",
            })
        elif "does not exist" in error_msg.lower():
            result.update({
                "error_type": "validation_error",
                "guidance": "Referenced record does not exist in the system.",
                "suggestion": "Verify that linked records (customers, items) exist.",
            })
        elif "permission" in error_msg.lower():
            result.update({
                "error_type": "permission_error",
                "guidance": "Insufficient permissions for this operation.",
            })
        else:
            result.update({
                "error_type": "general_error",
                "guidance": "Document creation failed due to validation or system error.",
            })
        return result