from .ai_client import client
from .utils import clean_state
import json

from ..agent_.tools import tool_agent_create, tool_validate_payload

tool_map = {
    "tool_agent_create": tool_agent_create,
    "tool_validate_payload": tool_validate_payload
}

# def supervisor_agent(state, agents):
#     """This is the main controller agents, controls flow of information to and from other agents"""

#     messages = state["messages"]
#     supervisor_agent_system_prompt = (
#         def supervisor_agent(state, agents):
#     """This is the main controller agents, controls flow of information to and from other agents"""

#     messages = state["messages"]
#     supervisor_agent_system_prompt = (

#             )
#     messages.insert(0, {"role": "system", "content": supervisor_agent_system_prompt})
#     )


def generate_doctype_payload_agent(state, tools=None):
    
    messages = state["messages"]

    generate_payload_system_prompt = (
            "You are an expert Frappe/ERPNext developer. Generate STRICT JSON only (no prose). "
            "The JSON should be a valid DocType payload with keys: doctype='DocType', name, module, custom, fields, permissions, autoname (if needed)."
            " If you cannot produce valid JSON, return an error object as JSON: {\"status\":\"error\",\"message\":\"...\"}."
            " you have access to the tool_validate_payload function to check the validity of the generated JSON."
            " You must use the tool_validate_payload function to ensure the generated JSON is valid before returning it."
)
    
    messages.insert(0, {"role": "system", "content": generate_payload_system_prompt})
    response = client(
        tools=tools,
        messages=messages
    )

    return response

def validate_doctype_payload_agent(state, tools=None):
    
    messages = state["messages"]
    ### UPDATE SYTEM PROMPT TO MIRROR AGENT
    generate_payload_system_prompt = (
            "You are an expert Frappe/ERPNext developer. Generate STRICT JSON only (no prose). "
             "You are the Validator Agent.\n"
            "The previous tool execution FAILED.\n"
            "Here is what happened:\n"
            f"this is the pyload that was genereated: {json.dumps(state['tool_messages'][-1], indent=2)}\n\n "
            f"{json.dumps(state['tool_messages'][-1], indent=2)}\n\n"
            "Your job is to FIX the payload and revalidate it."
            " you have access to the tool_validate_payload function to check the validity of the generated JSON."
            " You must use the tool_validate_payload function to ensure the generated JSON is valid before returning it."
)
    
    messages.insert(0, {"role": "system", "content": generate_payload_system_prompt})
    response = client(
        tools=tools,
        messages=messages
    )

    return response

def create_doctype_agent(state, tools=None):
    
    messages = state["messages"]
    payload = state.get("payload", {})

    # create and validate, "mirror -> regenerate -> create" agent
    generate_doctype_system_prompt = (
         "You are the Creator Agent. The input JSON is already validated. "
         "you have access to the tool_agent_create function to create the DocType in Frappe/ERPNext."
         f"this is the sanitized payload to create the DocType: {json.dumps(payload, indent=2)}.\n"
         "you must use the tool_agent_create function to create the DocType."
         "Call tool_agent_create with the sanitized payload. If creation succeeds, return {\"status\":\"ok\",\"created\": [ ... ]}. "
         "If creation fails, return {\"status\":\"error\",\"message\":\"...\",\"errors\":[...]}."

    )
    messages.insert(0, {
    "role": "system",
    "content": generate_doctype_system_prompt
})



    response = client(
        tools=tools,
        messages=messages
    )

    return response

def execute_tool_calls(state, message):
        tool_calls = message.get("tool_calls") or []
        tool_messages = []
        is_error = False

        for tool in tool_calls:
            name = tool.function.name
            args_json = tool.function.arguments or "{}"
            state["payload"] = {
                "name": name,
                "args": json.loads(args_json)
            }

            print(f"Executing tool: {name} with args: {args_json}")

            # Parse arguments
            try:
                parsed_args = json.loads(args_json)
            except Exception as e:
                is_error = True
                tool_messages.append({
                    "role": "function",
                    "tool_call_id": tool.id,
                    "name": name,
                    "content": f"JSON parse error: {str(e)}",
                })
                continue

            tool_function = tool_map.get(name)

            if not tool_function:
                is_error = True
                tool_messages.append({
                    "role": "function",
                    "tool_call_id": tool.id,
                    "name": name,
                    "content": f"Tool '{name}' not found.",
                })
                continue

            # Execute tool
            
            try:
                result = tool_function(**parsed_args)
                if result.get("status") == "error":
                    is_error = True
                tool_messages.append({
                    "role": "function",
                    "tool_call_id": tool.id,
                    "name": name,
                    "content": result if isinstance(result, dict) else json.loads(result), ####should be JSON.DUMPS
                })
            except Exception as e:
                is_error = True
                tool_messages.append({
                    "role": "function",
                    "tool_call_id": tool.id,
                    "name": name,
                    "content": f"Tool execution error: {str(e)}",
                })

        return state, is_error, tool_messages


# def route_validate(state):
#     if state["messages"][-1].get("tool_calls"):
#         return "execute_tool_calls"
#     else:
#         return "create_doctype_agent"

def route_tool_call(state, is_error):
    last_msg = state["tool_messages"][-1]

    content = last_msg.get("content") or {}
    status = content.get("status")
    status_agent_create = content.get("status_tool_agent_create")
    print(f"{is_error, status, status_agent_create}")
    print(f"{last_msg}")

    if is_error or status == "error":
        return state, validate_doctype_payload_agent

    if not is_error and status == "ok":
        return state, create_doctype_agent

    if status_agent_create == "error":
        return state, validate_doctype_payload_agent

    if status_agent_create == "ok":
        return state, "END"
    
    return state, validate_doctype_payload_agent

    
    
    

    
