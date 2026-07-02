# agent_builder/.hermes/plugins/frappe_tools/tools.py

import json
from agent_builder.native_api.tools.decorator import tool
import frappe

@tool(schema_name="frappe_get_doc")
def frappe_get_doc(args: dict, **kwargs) -> str:
    try:
        doc = frappe.get_doc(args["doctype"], args["name"])
        doc.check_permission("read")

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


@tool(schema_name="frappe_get_list")
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


@tool(schema_name="frappe_save_doc")
def frappe_save_doc(args: dict, **kwargs) -> str:
    
    try:
        data = args["doc"]
        doctype = data.get("doctype")
        name = data.get("name")

        if name and frappe.db.exists(doctype, name):
            # Update existing
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("write")
            
            for key, value in data.items():
                if key in ("name", "doctype", "modified", "creation", "owner", "docstatus", "idx"):
                    continue
                df = doc.meta.get_field(key)
                if df and (df.read_only or df.hidden or df.fieldtype == "Read Only"):
                    continue
                doc.set(key, value)
                

            doc.save()
        else:
            # Create new
            doc = frappe.get_doc(data)
            doc.check_permission("create")
            doc.insert(ignore_permissions=False)

        frappe.db.commit()
        return json.dumps({"name": doc.name, "doctype": doc.doctype, "status": "saved"})
    except frappe.PermissionError:
        return json.dumps({"error": "No permission to save this document"})
    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool(schema_name="frappe_execute_action")
def frappe_execute_action(args: dict, **kwargs) -> str:
    try:
        doctype = args.get("doctype")
        name = args.get("name")
        action = args.get("action")

        if not (doctype and name and action):
            return json.dumps({"error": "doctype, name, and action are required."})

        doc = frappe.get_doc(doctype, name)
        
        active_workflow = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1})
        
        if active_workflow:
            import frappe.model.workflow
            frappe.model.workflow.apply_workflow(doc, action)
            frappe.db.commit()
            return json.dumps({"doctype": doctype, "name": name, "status": "action_executed", "action": action})
        else:
            if action.lower() == "submit":
                doc.submit()
            elif action.lower() == "cancel":
                doc.cancel()
            else:
                return json.dumps({"error": f"Invalid action '{action}' for doctype without workflow."})
            
            frappe.db.commit()
            return json.dumps({"doctype": doctype, "name": name, "status": "action_executed", "action": action})

    except frappe.PermissionError:
        return json.dumps({"error": f"No permission to perform '{args.get('action')}' on {args.get('doctype')} '{args.get('name')}'"})
    except frappe.ValidationError as e:
        return json.dumps({"error": f"Validation failed: {str(e)}"})
    except Exception as e:
        return json.dumps({"error": str(e)})