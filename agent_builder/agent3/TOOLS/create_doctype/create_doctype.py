import frappe

def tool_create_doctype(payload: dict, dry_run: bool = False):
    """
    Create ANY Frappe document after validation.
    """
    try:
        doctype = payload.get("doctype")
        if not doctype:
            return {"status": "error", "error": "Missing doctype"}

        if dry_run:
            return {
                "status": "ok",
                "dry_run": True,
                "doctype": doctype
            }

        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "ok",
            "created": {
                "doctype": doc.doctype,
                "name": doc.name
            }
        }

    except Exception as e:
        frappe.db.rollback()
        return {
            "status": "error",
            "error": str(e)
        }
