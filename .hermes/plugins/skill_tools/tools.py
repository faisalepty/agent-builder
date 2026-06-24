# agent_builder/.hermes/plugins/frappe_tools/tools.py

import json
import frappe

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