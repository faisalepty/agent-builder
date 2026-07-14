# tools/frappe_tools/document_delete.py

import json
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="frappe_delete_doc")
def frappe_delete_doc(args: dict, **kwargs) -> str:
    try:
        doctype = args.get("doctype")
        name = args.get("name")
        force = args.get("force", False)

        if not doctype or not name:
            return json.dumps({"error": "Both doctype and name are required"})

        if not frappe.db.exists(doctype, name):
            return json.dumps({"error": f"{doctype} '{name}' not found", "doctype": doctype, "name": name})

        doc = frappe.get_doc(doctype, name)
        doc.check_permission("delete")

        frappe.delete_doc(doctype, name, force=force, ignore_permissions=False)
        frappe.db.commit()

        return json.dumps({"name": name, "doctype": doctype, "status": "deleted"})

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to delete this document"})

    except frappe.LinkExistsError:
        return json.dumps({
            "error": f"Cannot delete {doctype} '{name}': it is linked to other documents. Retry with force=true to override.",
            "error_type": "link_exists",
            "doctype": doctype,
            "name": name,
        })

    except Exception as e:
        return json.dumps({"error": str(e)})