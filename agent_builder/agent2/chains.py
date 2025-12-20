# ================================
# chains.py
# ================================
from ..agent1.ai_client import client
import json
from ..agent_.tools import tool_agent_create, tool_validate_dashboard_chart_payload, tool_get_doctype_metadata, tool_validate_doctype_payload



tool_map = {
    "tool_agent_create": tool_agent_create,
    "tool_validate_doctype_payload": tool_validate_doctype_payload,
    "tool_validate_dashboard_chart_payload": tool_validate_dashboard_chart_payload,
    "tool_get_doctype_metadata": tool_get_doctype_metadata
}

# ----------------
# SUPERVISOR AGENT
# ----------------

def supervisor_agent(state):
    """
    AI Supervisor:
    - Reads last tool result
    - Decides next agent
    - Outputs STRICT JSON: {"next_agent": "..."}
    """
    last_tool = state.get("last_tool_result") or {}
    has_error = state.get("has_error")

    state_summary = {
        "messages": state.get("messages"),
        "current_agent": state.get("current_agent"),
        "last_tool_called": state.get("last_tool_called"),
        "payload": state.get("payload"),
        "payload_is_validated": state.get("validated_payload") is not None,
        "has_error": has_error,
        "last_error": state.get("last_error"),
        "error_source": state.get("error_source"),
    }

    system_prompt = ("""
   You are the Supervisor Agent. You decide the NEXT action only. 
You do not generate payloads or call tools.

Available agents:
- generate_doctype_payload_agent
- generate_dashboard_chart_payload_agent
- regenerate_validate_doctype_payload_agent
- create_doctype_agent
"""
f"""
State Summary:
{json.dumps(state_summary, indent=2)}
"""
"""
Routing Logic:
1. Identify Intent: 
   - DocType/Custom Field? -> Use generate_doctype_payload_agent.
   - Dashboard/Chart? -> Use generate_dashboard_chart_payload_agent.
2. Validation Check:
   - If payload is not yet validated -> Send to the respective generator agent.
   - If validation fails (status: error) -> Send to regenerate_validate_doctype_payload_agent.
4. doctype metadata request:
    - if last tool call was get_doctype_metadata you MUST SEND  back to the current agent
3. Creation Check:
   - If validation succeeds (status: ok) AND not yet created -> Send to create_doctype_agent.
   - If creation fails (status: error) -> Send to regenerate_validate_doctype_payload_agent.
   - If creation succeeds (status: ok) -> END.


Constraints:
- Return ONLY a raw string in the format: { "next_agent": "...", "reason": "..." }
- No code fences, no prose, no explanations.

CORRECT FORMAT:
{ "next_agent": "create_doctype_agent", "reason": "Payload validated, proceeding to creation." }
"""
)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Decide next agent"}
    ]

    resp = client(messages=messages)
    return resp


# --------------------------------
# GENERATE DOCTYPE PAYLOAD AGENT
# --------------------------------

def generate_doctype_payload_agent(state, tools=None):
    state["entity_type"] = "doctype"

    system_prompt ="""
You are an expert Frappe/ERPNext developer.

Generate STRICT JSON only.

Keys:
- doctype: "DocType"
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

    messages = [
        {"role": "system", "content": system_prompt},
        *state["messages"],
    ]

    return client(messages=messages, tools=tools)


# --------------------------------
# GENERATE DASHBOARD CHART AGENT
# --------------------------------

def generate_dashboard_chart_payload_agent(state, tools=None):
    state["entity_type"] = "dashboard_chart"

    system_prompt = ("""You are a Frappe Framework Expert. Your task is to generate a 'Dashboard Chart' DocType payload.
Do NOT guess field names. Use the provided METADATA to ensure the fields exist.

### CORE LOGIC RULES:
1. IF METADATA IS EMPTY: Call 'tool_get_doctype_metadata' for the source DocType first.
2. IDENTIFY MODE:
   - CATEGORICAL: If grouping by a field (e.g., Pie, Donut). Set 'chart_type' to "Group By".
   - TIME SERIES: If x-axis is a date. Set 'chart_type' to ["Count", "Sum", "Average"].

### CONDITIONAL SCHEMA:

#### 1. CATEGORICAL (Group By) Mode:
- chart_type: "Group By"
- group_by_type: ["Count", "Sum", "Average"]
- group_by_based_on: Use a field from metadata (e.g., "status", "category").
- number_of_groups: 0

#### 2. TIME SERIES Mode:
- chart_type: ["Count", "Sum", "Average"]
- timeseries: 1
- based_on: Must be a Date or Datetime field from metadata (e.g., "posting_date").
- value_based_on: Numeric field (Required if chart_type is "Sum" or "Average").
- timespan: "Last Year" (default)
- time_interval: "Monthly" (default)

#### 3. COMMON FIELDS:
- doctype: "Dashboard Chart"
- document_type: The source DocType (e.g., "Sales Invoice").
- chart_name: Unique name.
- type: ["Line", "Bar", "Percentage", "Pie", "Donut"]
- filters_json: MUST be stringified JSON list of lists: "[[\"field\", \"op\", \"val\"]]" or "[]".
- is_public: 1
- is_standard: 0

### INSTRUCTIONS:
- Generate the JSON.
- You MUST call 'tool_validate_dashboard_chart_payload' with {"payload": <json>}.
""")

    messages = [
        {"role": "system", "content": system_prompt},
        *state["messages"],
    ]

    return client(messages=messages, tools=tools)


# --------------------------------
# VALIDATION AGENT (GENERIC)
# --------------------------------

def regenerate_validate_doctype_payload_agent(state, tools=None):
    state_summary = {
        "payload": state.get("payload"),
        "last_error": state.get("last_error"),
        "error_source": state.get("error_source"),
    }
    system_prompt = (
        "You are the Validator Agent.\n"
        "Previous validation or creation FAILED.\n"
        "Fix the payload and revalidate.\n"
        "You MUST always call the validate tool after fixing the payload"
        "State summary:\n"
        f"{json.dumps(state_summary, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        *state["messages"]
    ]

    return client(messages=messages, tools=tools)


# --------------------------------
# CREATE DOCTYPE AGENT
# --------------------------------

def create_doctype_agent(state, tools=None):
    payload = state.get("validated_payload") or state.get("payload")

    system_prompt = (
        "You are the Creator Agent.\n"
        "Payload is already validated.\n"
        "Call tool_agent_create to persist it.\n"
        f"Payload:\n{json.dumps(payload, indent=2)}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Create the document"},
    ]

    return client(messages=messages, tools=tools)


# --------------------------------
# TOOL EXECUTION
# --------------------------------

def execute_tool_calls(state, message):
    tool_calls = message.get("tool_calls") or []
    is_error = False

    for call in tool_calls:
        # 1. Access nested function details
        func_info = call.get("function", {})
        name = func_info.get("name")
        args_str = func_info.get("arguments") or "{}"

        state["last_tool_called"] = name

        try:
            # 2. CRITICAL: Parse the JSON string into a dict
            if isinstance(args_str, str):
                args_dict = json.loads(args_str)
            else:
                args_dict = args_str

            # 3. Now you can safely unpack the dictionary
            result = tool_map[name](**args_dict)
            
            state["last_tool_result"] = result

            if isinstance(result, dict) and result.get("status") in ("error", "failed"):
                is_error = True
                state["last_error"] = json.dumps(result)
                state["error_source"] = name
            else:
                if isinstance(result, dict) and "sanitized_payload" in result:
                    state["validated_payload"] = result["sanitized_payload"]

        except Exception as e:
            is_error = True
            state["last_error"] = str(e)
            state["error_source"] = name
            print(f"Error executing tool {name}: {e}") # Debugging

    state["has_error"] = is_error
    return state, is_error

