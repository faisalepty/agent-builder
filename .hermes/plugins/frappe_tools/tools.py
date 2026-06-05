# agent_builder/.hermes/plugins/frappe_tools/tools.py

import json
import frappe

def frappe_get_doc(args: dict, **kwargs) -> str:
    try:
        doc = frappe.get_doc(args["doctype"], args["name"])

        return json.dumps(doc.as_dict(), default=str)

    except frappe.DoesNotExistError:
        return json.dumps({
            "error": f"{args['doctype']} '{args['name']}' does not exist"
        })

    except frappe.PermissionError:
        return json.dumps({
            "error": f"No permission to read {args['doctype']} '{args['name']}'"
        })

    except Exception as e:
        return json.dumps({"error": str(e)})


def frappe_get_list(args: dict, **kwargs) -> str:
    try:
        result = frappe.get_list(
            args["doctype"],
            filters=args.get("filters", {}),
            fields=args.get("fields", ["name"]),
            limit_page_length=args.get("limit", 20),
        )

        return json.dumps(result, default=str)

    except frappe.PermissionError:
        return json.dumps({
            "error": f"No permission to read {args['doctype']}"
        })

    except Exception as e:
        return json.dumps({"error": str(e)})


def frappe_save_doc(args: dict, **kwargs) -> str:
    
    try:
        data = args["doc"]
        doctype = data.get("doctype")
        name = data.get("name")

        if name and frappe.db.exists(doctype, name):
            # Update existing
            doc = frappe.get_doc(doctype, name)
            doc.update(data)
            doc.save()
        else:
            # Create new
            doc = frappe.get_doc(data)
            doc.insert(ignore_permissions=False)

        frappe.db.commit()
        return json.dumps({"name": doc.name, "doctype": doc.doctype, "status": "saved"})
    except frappe.PermissionError:
        return json.dumps({"error": "No permission to save this document"})
    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def frappe_delete_doc(args: dict, **kwargs) -> str:
    try:
        frappe.delete_doc(args["doctype"], args["name"])
        frappe.db.commit()
        return json.dumps({"doctype": args["doctype"], "name": args["name"], "status": "deleted"})
    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to delete {args['doctype']} '{args['name']}'"})
    except Exception as e:
        return json.dumps({"error": str(e)})