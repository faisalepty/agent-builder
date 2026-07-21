# omnis_hermes/tools/internal/view_skill.py
import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="view_skill")
def view_skill(args: dict, **kwargs) -> str:
	try:
		skill_name = args.get("skill_name")
		if not skill_name:
			return json.dumps({"error": "Skill name is required"})

		skill_doc = frappe.get_doc("Skill", skill_name)
		skill_description = skill_doc.get("description", "")
		skill_content = skill_doc.get("content", "")
		return json.dumps(
			{"name": skill_doc.name, "description": skill_description, "content": skill_content}, default=str
		)

	except frappe.DoesNotExistError:
		return json.dumps({"error": f"Skill '{skill_name}' does not exist"})
	except frappe.PermissionError:
		return json.dumps({"error": f"No permission to view skill '{skill_name}'"})
	except Exception as e:
		return json.dumps({"error": str(e)})
