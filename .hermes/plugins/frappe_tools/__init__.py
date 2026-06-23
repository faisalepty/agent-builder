# agent_builder/.hermes/plugins/frappe_tools/__init__.py
from pathlib import Path

from . import tools, schemas

def register(ctx):
    ctx.register_tool(
        name="frappe_get_doc",
        toolset="frappe_tools",
        schema=schemas.FRAPPE_GET_DOC,
        handler=tools.frappe_get_doc,
    )
    ctx.register_tool(
        name="frappe_get_list",
        toolset="frappe_tools",
        schema=schemas.FRAPPE_GET_LIST,
        handler=tools.frappe_get_list,
    )
    ctx.register_tool(
        name="frappe_save_doc",
        toolset="frappe_tools",
        schema=schemas.FRAPPE_SAVE_DOC,
        handler=tools.frappe_save_doc,
    )
    ctx.register_tool(
        name="frappe_delete_doc",
        toolset="frappe_tools",
        schema=schemas.FRAPPE_DELETE_DOC,
        handler=tools.frappe_delete_doc,
    )
    ctx.register_tool(
        name="view_skill",
        toolset="frappe_tools",
        schema=schemas.VIEW_SKILL,
        handler=tools.view_skill,
    )
    ctx.register_tool(
        name="list_skills",
        toolset="frappe_tools",
        schema=schemas.LIST_SKILLS,
        handler=tools.list_skills,
    )

    # Bundle the skill
    # skills_dir = Path(__file__).parent / "skills"
    # for child in sorted(skills_dir.iterdir()):
    #     skill_md = child / "SKILL.md"
    #     if child.is_dir() and skill_md.exists():
    #         ctx.register_skill(child.name, skill_md)