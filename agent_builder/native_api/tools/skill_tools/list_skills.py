# omnis_hermes/tools/internal/skill_list.py
import json
import frappe
from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="list_skills")
def list_skills(args: dict, **kwargs) -> str:
    try:
        skills = frappe.get_list("Skill", fields=["name", "description"], limit_page_length=args.get("limit", 20))
        return json.dumps(skills, default=str)

    except frappe.PermissionError:
        return json.dumps({"error": "No permission to list skills"})
    except Exception as e:
        return json.dumps({"error": str(e)})