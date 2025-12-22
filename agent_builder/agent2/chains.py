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


    state_summary = {
        "messages": state.get("messages"),
        "current_agent": state.get("current_agent"),
        "last_tool_called": state.get("last_tool_called"),
        "payload": state.get("payload"),
        "payload_is_validated": state.get("validated_payload") is not None,
        "has_error": state.get("has_error"),
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
   - If creation succeeds (status: ok) -> next_agent = "END".


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

    system_prompt = """
You are an Expert Frappe Framework Architect. Generate a VALID JSON schema for a NEW DocType.

PERMISSION GOVERNANCE (CRITICAL):
- Default: "is_submittable": 0.
- If is_submittable = 0 or omitted:
  - DO NOT include submit, cancel, or amend in permissions.
- ONLY if user mentions Submit, Approve, or Workflow:
  - Set "is_submittable": 1
  - Then allow submit, cancel, amend = 1.
- Never violate this rule.

SCHEMA CONSTRAINTS:
- doctype: DocType.
- Fieldnames: lowercase_with_underscores.
- Use ONLY fields that exist in DocType metadata.
- Mandatory field: "module".
- Child tables: fields, permissions, actions, links, states (arrays only).

ALLOWED FIELDTYPES:
Autocomplete, Attach, Attach Image, Barcode, Button, Check, Code, Color,
Currency, Data, Date, Datetime, Duration, Dynamic Link, Float, Geolocation,
Heading, HTML, HTML Editor, Icon, Image, Int, JSON, Link, Long Text,
Markdown Editor, Password, Percent, Phone, Read Only, Rating, Select,
Signature, Small Text, Table, Table MultiSelect, Text, Text Editor, Time.

FIELD ATTRIBUTE MAPPING:
- Mandatory → reqd: 1
- Unique → unique: 1
- Searchable → in_global_search: 1
- Show in List → in_list_view: 1
- Link → options: "TargetDocType" DO NOT GUESS fall back to Data if no information about target is provided
- Select → options: "A\\nB\\nC"

NAMING:
- naming_rule and autoname are separate.
- Set BOTH only if user specifies naming.
- Otherwise omit both.

CORE DOCTYPE:
{
  "doctype": "DocType",
  "name": "SingularCamelCase",
  "module": "Agent Builder",
  "custom": 1,
  "is_submittable": 0,
  "track_changes": 1,
  "fields": [],
  "permissions": [
    {
      "role": "System Manager",
      "read": 1, "write": 1, "create": 1, "delete": 1,
      "select": 1, "export": 1, "print": 1, "report": 1,
      "submit": 0, "cancel": 0, "amend": 0
    }
  ]
}

MODULE:
- If user specifies module → use it.
- Else → use "Agent Builder".

EXECUTION:
- Output STRICT JSON only.
- Call tool_validate_payload as FINAL and ONLY action.

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


def generate_number_card_payload_agent(state, tools=None):
    state["entity_type"] = "number_card"

    # Fetch metadata if available to help the LLM pick the right fields
    metadata_context = json.dumps(state.get('metadata', {}), indent=2)

    system_prompt = f"""You are a Frappe Framework Expert. Your task is to generate a 'Number Card' DocType payload.
Do NOT guess field names. Use the provided METADATA to ensure the fields exist.


### CORE LOGIC RULES:
1. IF METADATA IS EMPTY: Call 'tool_get_doctype_metadata' for the source DocType first.
2. AGGREGATE TYPE: 
   - Set 'type' to "Document Type" for standard DocType aggregation.
   - Set 'function' to ["Count", "Sum", "Average", "Minimum", "Maximum"].

### SCHEMA DEFINITION (Number Card):
- doctype: Always "Number Card"
- label: The display title of the card.
- document_type: The source DocType (e.g., "Sales Invoice").
- function: The calculation type (e.g., "Sum").
- aggregate_function_based_on: The numeric field to calculate (Required unless function is "Count").
- is_public: 1
- show_full_number: 1 (to show 1,234,567) or 0 (to show 1.2M).
- show_percentage_stats: 1 (to show trend) or 0.
- stats_time_interval: ["Daily", "Weekly", "Monthly", "Yearly"] (Required if show_percentage_stats is 1).
- filters_json: MUST be stringified JSON list of lists: "[[\"field\", \"op\", \"val\"]]" or "[]".
- module: "Agent Builder" (default).

### INSTRUCTIONS:
- Generate the JSON.
- You MUST call 'tool_validate_number_card_payload' with {{"payload": <json>}}.
- Output ONLY the tool call. No prose.
"""

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
        "without changing the structure, correct the payload.\n"
        "Do NOT alter the intent or fields specified by the user.\n"
        "unless there is an error attached to the value or key you want to change, do not change anything.\n"
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

