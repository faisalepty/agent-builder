from .ai_client import client
from .utils import clean_state
import json

from ..agent_.tools import tool_agent_create, tool_validate_payload

tool_map = {
    "tool_agent_create": tool_agent_create,
    "tool_validate_payload": tool_validate_payload
}


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

    # create and validate, "mirror -> regenerate -> create" agent
    generate_doctype_system_prompt = (
         "You are the Creator Agent. The input JSON is already validated. "
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

def execute_tool_calls(message):
        tool_calls = message.get("tool_calls") or []
        tool_messages = []
        is_error = False

        for tool in tool_calls:
            name = tool.function.name
            args_json = tool.function.arguments or "{}"

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

        return is_error, tool_messages


# def route_validate(state):
#     if state["messages"][-1].get("tool_calls"):
#         return "execute_tool_calls"
#     else:
        return "create_doctype_agent"
    
def route_tool_call(state, is_error):
    status = state["messages"][-1].get("status")
    if is_error or status == "error":
        return validate_doctype_payload_agent
    else:
        return create_doctype_agent
    

    
