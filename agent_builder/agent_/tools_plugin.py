# aiplugin.py
agent_tools = [
    {
      "type": "function",
      "function": {
        "name": "tool_validate_payload",
        "description": "Validate a DocType payload",
        "parameters": {
          "type": "object",
          "properties": {
            "payload": {"type": "object"},
            "strict": {"type": "boolean"}
          },
          "required": ["payload"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "tool_agent_create",
        "description": "Create DocType after validation",
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
