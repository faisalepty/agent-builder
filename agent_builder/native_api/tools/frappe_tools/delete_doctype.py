import frappe
from typing import Any, Dict

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="delete_document")
def delete_document(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an existing document"""
    doctype = arguments.get("doctype")
    name = arguments.get("name")
    force = arguments.get("force", False)

    # Check permission for DocType
    if not frappe.has_permission(doctype, "delete"):
        return {"success": False, "error": f"Insufficient permissions to delete {doctype} document"}

    try:
        # Check if document exists
        if not frappe.db.exists(doctype, name):
            return {
                "success": False,
                "error": f"{doctype} '{name}' not found",
                "doctype": doctype,
                "name": name,
            }

        # Get document first to check for dependencies and permissions
        try:
            doc = frappe.get_doc(doctype, name)
        except frappe.PermissionError:
            return {
                "success": False,
                "error": f"Insufficient permissions to access {doctype} '{name}'",
                "doctype": doctype,
                "name": name,
            }
        except Exception as get_error:
            return {
                "success": False,
                "error": f"Failed to access {doctype} '{name}': {str(get_error) or 'Unknown error accessing document'}",
                "doctype": doctype,
                "name": name,
            }

        # Delete document
        try:
            if force:
                frappe.delete_doc(doctype, name, force=True)
            else:
                frappe.delete_doc(doctype, name)

            frappe.db.commit()

            return {
                "success": True,
                "doctype": doctype,
                "name": name,
                "message": f"{doctype} '{name}' deleted successfully",
            }

        except frappe.LinkExistsError as link_error:
            return {
                "success": False,
                "error": f"Cannot delete {doctype} '{name}' because it is linked to other documents. Use force=true to override.",
                "doctype": doctype,
                "name": name,
                "dependency_error": True,
            }
        except frappe.PermissionError as perm_error:
            return {
                "success": False,
                "error": f"Insufficient permissions to delete {doctype} '{name}': {str(perm_error) or 'Permission denied'}",
                "doctype": doctype,
                "name": name,
                "permission_error": True,
            }
        except Exception as delete_error:
            error_msg = str(delete_error) or f"Unknown error occurred while deleting {doctype} '{name}'"
            return {
                "success": False,
                "error": error_msg,
                "doctype": doctype,
                "name": name,
                "delete_error": True,
            }

    except Exception as e:
        error_msg = (
            str(e) or f"Unexpected error occurred while processing delete request for {doctype} '{name}'"
        )

        frappe.log_error(
            title=_("Document Delete Error"), message=f"Error deleting {doctype} '{name}': {error_msg}"
        )

        return {
            "success": False,
            "error": error_msg,
            "doctype": doctype,
            "name": name,
            "general_error": True,
        }
