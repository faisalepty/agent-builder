# agent_builder/.hermes/plugins/frappe_tools/__init__.py
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