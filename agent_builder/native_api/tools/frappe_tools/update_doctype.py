from typing import Dict, Any

import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="update_document")
def update_document(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing document"""
    doctype = arguments.get("doctype")
    name = arguments.get("name")
    data = arguments.get("data", {})

    # Reject direct updates to child-table doctypes. Saving a child row in isolation
    # bypasses the parent's validate() pipeline, so derived fields (e.g. ERPNext's
    # row `amount` and parent `total`/`total_qty`/`grand_total`) never recompute.
    try:
        child_meta = frappe.get_meta(doctype)
    except Exception:
        child_meta = None

    if child_meta is not None and getattr(child_meta, "istable", 0):
        parent_info: Dict[str, Any] = {
            "success": False,
            "error": (
                f"'{doctype}' is a child-table doctype and cannot be updated directly. "
                f"Update the parent document instead and pass the child rows under the table fieldname in `data`."
            ),
            "error_type": "child_doctype_direct_update",
            "child_doctype": doctype,
        }

        # Try to resolve the parent doc + table fieldname so the model can fix its call.
        if name:
            try:
                parent_name = frappe.db.get_value(doctype, name, "parent")
                parent_type = frappe.db.get_value(doctype, name, "parenttype")
                parent_field = frappe.db.get_value(doctype, name, "parentfield")
                if parent_name and parent_type and parent_field:
                    parent_info["parent_doctype"] = parent_type
                    parent_info["parent_name"] = parent_name
                    parent_info["parent_table_fieldname"] = parent_field
                    parent_info["suggestion"] = (
                        f"Call update_document with doctype='{parent_type}', "
                        f"name='{parent_name}', and data={{'{parent_field}': "
                        f"[{{'name': '{name}', ...fields to change...}}]}}. "
                        f"Patch mode will update only the named row; other rows are untouched."
                    )
            except Exception:
                pass

        return parent_info

    try:
        # Check if document exists
        if not frappe.db.exists(doctype, name):
            return {"success": False, "error": f"{doctype} '{name}' not found"}

        # 1. Native Frappe Doctype-Level Write Permission Check
        if not frappe.has_permission(doctype, "write", doc=name):
            return {
                "success": False,
                "error": f"Insufficient permissions to update {doctype} '{name}'."
            }

        # Get document
        doc = frappe.get_doc(doctype, name)

        # Enhanced document state validation
        current_docstatus = getattr(doc, "docstatus", 0)
        current_workflow_state = getattr(doc, "workflow_state", None)

        # Check if document is cancelled
        if current_docstatus == 2:
            return {
                "success": False,
                "error": f"Cannot modify cancelled document {doctype} '{name}'. Cancelled documents are read-only.",
                "docstatus": current_docstatus,
                "workflow_state": current_workflow_state,
                "suggestion": "Use document_get to view the cancelled document, or create a new document if needed.",
            }

        # 2. Native System & Sensitive Field Filtering
        meta = frappe.get_meta(doctype)
        table_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Table"}
        
        system_fields = {"owner", "creation", "modified", "modified_by", "docstatus", "idx"}
        sensitive_fieldtypes = {"Password"}
        
        restricted_fields_attempted = []
        for field in data.keys():
            # Bypass top-level system check for child tables (Frappe handles inner system fields dynamically)
            if field in table_fields:
                continue

            if field in system_fields:
                restricted_fields_attempted.append(field)
                continue
                
            df = meta.get_field(field)
            if df and df.fieldtype in sensitive_fieldtypes:
                restricted_fields_attempted.append(field)

        if restricted_fields_attempted:
            return {
                "success": False,
                "error": f"Cannot update system or restricted fields: {', '.join(restricted_fields_attempted)}.",
            }

        # 3. Apply updates using Frappe's native update pipeline
        # doc.update() natively routes child-table lists to doc.set() or doc.extend(), 
        # applying patches automatically if 'name' is provided in the child row dict.
        doc.update(data)

        # 4. Save document
        # ignore_permissions=False ensures native Field Level Permissions are enforced.
        doc.save(ignore_permissions=False)

        # Get updated document state
        doc.reload()
        updated_docstatus = getattr(doc, "docstatus", 0)
        updated_workflow_state = getattr(doc, "workflow_state", None)

        result = {
            "success": True,
            "name": doc.name,
            "doctype": doctype,
            "updated_fields": list(data.keys()),
            "docstatus": updated_docstatus,
            "state_description": "Draft" if updated_docstatus == 0 else ("Submitted" if updated_docstatus == 1 else "Unknown"),
            "workflow_state": updated_workflow_state,
            "owner": doc.owner,
            "modified": str(doc.modified),
            "modified_by": doc.modified_by,
            "message": f"{doctype} '{doc.name}' updated successfully",
        }

        # Check if user can submit this document
        if updated_docstatus == 0:
            try:
                result["can_submit"] = frappe.has_permission(doctype, "submit", doc=doc.name)
            except Exception:
                result["can_submit"] = False
        else:
            result["can_submit"] = False

        # Add useful next steps information
        if updated_docstatus == 0:
            result["next_steps"] = [
                "Document remains in draft state",
                "You can continue updating this document",
                f"Submit permission: {'Available' if result['can_submit'] else 'Not available'}",
            ]
            if updated_workflow_state:
                result["next_steps"].append(f"Current workflow state: {updated_workflow_state}")
        else:
            result["next_steps"] = [
                f"Document state: {result['state_description']}",
                "Further modifications may be restricted to 'Allow on Submit' fields only",
            ]

        return result

    except Exception as e:
        frappe.log_error(title="Document Update Error", message=f"Error updating {doctype} '{name}': {str(e)}")
        error_msg = str(e)
        result = {"success": False, "error": error_msg, "doctype": doctype, "name": name}
        
        if "permission" in error_msg.lower():
            result["error_type"] = "permission_error"
            result["guidance"] = "Insufficient permissions for this operation or attempting to update a read-only field."
            
        return result