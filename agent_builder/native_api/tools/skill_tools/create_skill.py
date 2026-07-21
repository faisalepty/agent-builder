# tools/skill_tools/create_skill.py
import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="create_skill")
def create_skill(args: dict, **kwargs) -> str:
	"""Create a new Skill document."""
	name_ = args.get("name")
	description = args.get("description")
	if not name_:
		return json.dumps({"error": "name is required"})
	if not description:
		return json.dumps({"error": "description is required"})

	parent_skill = args.get("parent_skill")
	reference_slug = args.get("reference_slug")

	if (
		parent_skill
		and frappe.db.exists("Skill", parent_skill)
		and frappe.db.get_value("Skill", parent_skill, "parent_skill")
	):
		return json.dumps(
			{
				"error": (
					f"'{parent_skill}' is itself a nested skill and cannot be used as a parent. "
					"Only top-level skills may have children."
				),
				"error_type": "invalid_parent",
				"parent_skill": parent_skill,
			}
		)

	docname = f"{parent_skill}-{frappe.scrub(reference_slug)}" if parent_skill else frappe.scrub(name_)
	if frappe.db.exists("Skill", docname):
		return json.dumps(
			{
				"error": f"Skill '{docname}' already exists. Use a different name or update the existing skill.",
				"error_type": "already_exists",
				"name": docname,
			}
		)

	field_map = {
		"name": "name_",
		"description": "description",
		"is_enabled": "is_enabled",
		"disable_model_invocation": "disable_model_invocation",
		"argument_hint": "argument_hint",
		"parent_skill": "parent_skill",
		"reference_slug": "reference_slug",
		"domain": "domain",
		"content": "content",
		"attach": "attach",
		"server_script": "server_script",
		"metadata": "metadata",
	}

	try:
		doc = frappe.get_doc({"doctype": "Skill"})
		doc.check_permission("create")

		for arg_key, field_name in field_map.items():
			if arg_key in args and args[arg_key] is not None:
				value = args[arg_key]
				if field_name == "metadata" and isinstance(value, (dict, list)):
					value = json.dumps(value)
				doc.set(field_name, value)

		if parent_skill and not doc.reference_slug:
			return json.dumps(
				{
					"error": "reference_slug is required when parent_skill is set",
					"error_type": "missing_required_field",
					"missing_fields": ["reference_slug"],
				}
			)

		doc.insert(ignore_permissions=False)
		frappe.db.commit()

		return json.dumps(
			{
				"name": doc.name,
				"name_": doc.name_,
				"description": doc.description,
				"is_enabled": doc.is_enabled,
				"parent_skill": doc.parent_skill,
				"status": "created",
			},
			default=str,
		)

	except frappe.PermissionError:
		return json.dumps({"error": "No permission to create a Skill"})
	except frappe.MandatoryError as e:
		missing = [f.strip() for f in str(e).partition(": ")[2].split(",") if f.strip()]
		return json.dumps(
			{
				"error": f"Missing required fields: {', '.join(missing)}" if missing else str(e),
				"error_type": "missing_required_field",
				"missing_fields": missing,
			}
		)
	except frappe.ValidationError as e:
		return json.dumps({"error": f"Validation failed: {e!s}"})
	except Exception as e:
		frappe.log_error(title="Skill Create Error", message=f"Error creating skill '{name_}': {e!s}")
		return json.dumps({"error": str(e)})
