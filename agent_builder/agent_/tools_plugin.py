# aiplugin.py
agent_tools = [
   {
        "type": "function",
        "function": {
            "name": "tool_get_doctype_metadata",
            "description": "Fetch metadata for a DocType, used by generate Dashboard agents to get the fields and data for a document avoid hallucination",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctype": {"type": "string"}
                },
                "required": ["doctype"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_validate_doctype_payload",
            "description": "Validate any Frappe DocType payload",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object"}
                },
                "required": ["payload"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_validate_dashboard_chart_payload",
            "description": "Validate a Dashboard Chart payload with semantic checks",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object"}
                },
                "required": ["payload"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_agent_create",
            "description": "Create a Frappe document (DocType, Dashboard, Chart, Workspace, etc.) after validation",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {"type": "object"},
                    "dry_run": {"type": "boolean"}
                },
                "required": ["payload"]
            }
        }
    },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "tool_doctype_exists",
    #     "description": "Check if DocType exists",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"name": {"type": "string"}},
    #       "required": ["name"]
    #     }
    #   }
    # },
    # {
    #   "type": "function",
    #   "function": {
    #     "name": "tool_role_exists",
    #     "description": "Check if Role exists",
    #     "parameters": {
    #       "type": "object",
    #       "properties": {"role": {"type": "string"}},
    #       "required": ["role"]
    #     }
    #   }
    # }
]
