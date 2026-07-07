from typing import Dict, Any
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="list_documents")
def list_doctypes(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """List documents with filters"""
    doctype = arguments.get("doctype")
    filters = arguments.get("filters", {})
    fields = arguments.get("fields", ["name", "creation", "modified"])
    limit = arguments.get("limit", 20)
    order_by = arguments.get("order_by", "creation desc")

    current_user = frappe.session.user

    try:
        # 1. Native Frappe Doctype-Level Read Permission Check
        if not frappe.has_permission(doctype, "read"):
            return {
                "success": False,
                "error": f"Insufficient permissions to read {doctype} records."
            }

        # 2. Strict Guardrail for User DocType (Non-Administrators can only see their own row)
        if doctype == "User" and current_user != "Administrator":
            if not isinstance(filters, dict):
                filters = {}
            filters["name"] = current_user

        # 3. Dynamic Sensitive Field Filtering (Strip out Password field types)
        meta = frappe.get_meta(doctype)
        allowed_fields = []
        
        for field in fields:
            # Always allow standard system/virtual attributes
            if field in {"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx"}:
                allowed_fields.append(field)
                continue
            
            df = meta.get_field(field)
            if df:
                # Natively skip fields defined with a Password fieldtype
                if df.fieldtype == "Password":
                    continue
                allowed_fields.append(field)

        # Fallback if all requested fields were stripped
        if not allowed_fields:
            allowed_fields = ["name"]
            
        fields = allowed_fields

        # 4. Fetch documents using Frappe's native permission-aware list API.
        # Setting ignore_permissions=False ensures standard User Permissions and Roles are enforced.
        documents = frappe.get_list(
            doctype,
            filters=filters,
            fields=fields,
            limit=limit,
            order_by=order_by,
            ignore_permissions=False,
        )

        # 5. Get permission-aware total count for pagination info.
        total_count = 0
        try:
            # Modern Frappe syntax (v15/v16 style)
            count_result = frappe.get_list(
                doctype,
                filters=filters,
                fields=[{"COUNT": "name", "as": "count"}],
                limit=1,
                ignore_permissions=False,
            )
            total_count = count_result[0].get("count", 0) if count_result else 0
        except Exception:
            try:
                # Fallback to standard SQL-string aggregate syntax (v14 style)
                count_result = frappe.get_list(
                    doctype,
                    filters=filters,
                    fields=["count(name) as count"],
                    limit=1,
                    ignore_permissions=False,
                )
                total_count = count_result[0].get("count", 0) if count_result else 0
            except Exception:
                # Safe fallback if both aggregations fail under tight environment rules
                total_count = len(documents)

        return {
            "success": True,
            "doctype": doctype,
            "data": documents,
            "count": len(documents),
            "total_count": total_count,
            "has_more": total_count > limit,
            "filters_applied": filters,
            "message": f"Found {len(documents)} {doctype} records",
        }

    except Exception as e:
        frappe.log_error(title="Document List Error", message=f"Error listing {doctype}: {str(e)}")
        return {
            "success": False, 
            "error": str(e), 
            "doctype": doctype
        }