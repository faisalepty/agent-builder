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

def view_skill(args: dict, **kwargs) -> str:
    try:
        skill_name = args.get("skill_name")
        if not skill_name:
            return json.dumps({"error": "Skill name is required"})

        skill_doc = frappe.get_doc("Skill", skill_name)
        skill_description = skill_doc.get("description", "")
        skill_content = skill_doc.get("content", "")
        return json.dumps({
            "name": skill_doc.name,
            "description": skill_description,
            "content": skill_content
        }, default=str)


    except frappe.DoesNotExistError:
        return json.dumps({"error": f"Skill '{skill_name}' does not exist"})
    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to view skill '{skill_name}'"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def list_skills(args: dict, **kwargs) -> str:
    try:
        skills = frappe.get_list("Skill", fields=["name", "description"], limit_page_length=args.get("limit", 20))
        return json.dumps(skills, default=str)

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to list skills"})
    except Exception as e:
        return json.dumps({"error": str(e)})