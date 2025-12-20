import json
from .ai_client import client
from ..agent_.tools import tool_agent_create, tool_validate_dashboard_chart_payload, tool_get_doctype_metadata, tool_validate_doctype_payload

tool_map = {
    "tool_agent_create": tool_agent_create,
    "tool_validate_doctype_payload": tool_validate_doctype_payload,
    "tool_validate_dashboard_chart_payload": tool_validate_dashboard_chart_payload,
    "tool_get_doctype_metadata": tool_get_doctype_metadata
}


# -------------------------
# SUPERVISOR AGENT
# -------------------------
def supervisor_agent(state, tools=None):
    """
    AI Supervisor.
    Decides what agent should act next based on tool results.
    """

    last_tool_msg = state["tool_messages"][-1] if state["tool_messages"] else {}

    supervisor_prompt = f"""You are the Supervisor Agent.

Decide the next action using ONLY the state below.
Do not guess. Do not invent.

State:
{{supervisor_view}}

Rules:
- If last_tool_status == "error" → validate_payload_agent
- If last_tool_status == "ok" and last_tool == validation → create_entity_agent
- If last_tool_status == "ok" and last_tool == create → END
-if last_tool 

Return JSON:
{ "next_action": "...", "reason": "..." }
Where:
- next_action: one of [validate_doctype_payload_agent, create_entity_agent, END]
- reason: brief explanation of your decision

"""

    messages = [{"role": "system", "content": supervisor_prompt}]
    response = client(messages=messages)

    return response


# -------------------------
# GENERATE PAYLOAD AGENT
# -------------------------
def generate_doctype_payload_agent(state, tools=None):


    print("Agent: generate_doctype_payload_agent called")
    system_prompt = """
You are an expert Frappe/ERPNext developer.

Generate STRICT JSON only.

Keys:
- doctype: "Doctype"
- name
- module
- custom
- fields
- permissions
- autoname (optional)

You MUST call tool_validate_payload before returning.
You are NOT ALLOWED to call any other tool apart from tool_validate payload
You MUST ONLY generate Payloads for doctype creation and call validation tool, do not call any other tool

If you cannot produce valid JSON:
{"status":"error","message":"..."}
"""

    messages = [{"role": "system", "content": system_prompt}] + state["messages"]

    return client(messages=messages, tools=tools)


def generate_dashboard_payload_agent(state, tools=None):
    print("Agent: generate_dashboard_payload_agent called")

    system_prompt = f"""
You are an expert Frappe/ERPNext Dashboard Chart payload generator.

you must generate STRICT JSON only.
Do NOT guess any fields, You MUST use tool_get_doctype_metadata to get field and Doctype information if the metadata is not available.

here is the doctype metadata provided by tool_get_doctype_metadata :
{json.dumps(state.get('metadata', {}), indent=2) or "{}"}

if metadata is empty, you MUST call tool_get_doctype_metadata to get the metadata.
if metadata is available, use it to generate the Dashboard chart payload and you must call tool_validate_dashboard_payload to validate Payload.

"""
    messages = [{"role": "system", "content": system_prompt}] + state["messages"]

    return client(messages=messages, tools=tools)


# -------------------------
# VALIDATOR AGENT
# -------------------------
def validate_doctype_payload_agent(state, tools=None):
    print("Agent: validate_doctype_payload_agent called")
    last_tool = state["tool_messages"][-1]

    system_prompt = f"""
You are the VALIDATOR AGENT.

The previous attempt FAILED.

Tool output:
{json.dumps(last_tool, indent=2)}

this is the payload that was generated:
{json.dumps(state['payload'], indent=2)}

Fix the payload and re-validate.

You MUST always call tool_validate_doctype_payload if the payload generated is for a DocType else you must call tool_validate_dashboard_chart_payload if the payload generated is for a Dashboard Chart.
"""

    messages = [{"role": "system", "content": system_prompt}] + state["messages"]

    return client(messages=messages, tools=tools)


# -------------------------
# CREATE AGENT
# -------------------------
def create_doctype_agent(state, tools=None):
    print("Agent: create_doctype_agent called")
    payload = state["payload"]

    system_prompt = f"""
You are the CREATOR AGENT.
The payload is already validated and ready for creation, DO NOT REVALIDATE.
you have the following payload to create the DocType Or a Dashboard Chart:


Payload:
{json.dumps(payload, indent=2)}

you must always call tool_agent_create. to create the DocType.

"""

    messages = [{"role": "system", "content": system_prompt}] + state["messages"]

    return client(messages=messages, tools=tools)


# -------------------------
# TOOL EXECUTOR
# -------------------------
def execute_tool_calls(state, message):
    is_error = False
    tool_messages = []

    for tool_call in message.get("tool_calls", []):
        name = tool_call.function.name
        args_raw = tool_call.function.arguments or "{}"

        try:
            args = json.loads(args_raw)
        except Exception as e:
            is_error = True
            tool_messages.append({
                "name": name,
                "content": {
                    "status": "error",
                    "message": f"JSON parse error: {str(e)}"
                }
            })
            continue

        tool_fn = tool_map.get(name)
        if not tool_fn:
            is_error = True
            tool_messages.append({
                "name": name,
                "content": {
                    "status": "error",
                    "message": f"Tool '{name}' not found"
                }
            })
            continue

        try:
            result = tool_fn(**args)

            if isinstance(result, str):
                result = json.loads(result)

            if result.get("status") == "error":
                is_error = True

            # Save validated payload
            if name == "tool_validate_payload" and result.get("status") == "ok":
                state["payload"] = args

            if name == "tool_get_doctype_metadata" and result.get("status") == "ok":
                state["metadata"] = result.get("Fields", [])

            tool_messages.append({
                "name": name,
                "content": result
            })

        except Exception as e:
            is_error = True
            tool_messages.append({
                "name": name,
                "content": {
                    "status": "error",
                    "message": str(e)
                }
            })

    state["tool_messages"].extend(tool_messages)
    return state, is_error

