from .chains import generate_doctype_payload_agent, create_doctype_agent, validate_doctype_payload_agent
from typing import TypedDict, List
import json
from ..agent_.tools import tool_agent_create
from ..agent_.tools_plugin import agent_tools as tool_schema


class State(TypedDict):
    system_message: str
    messages: List


tool_map = {
    "create_doctype": tool_agent_create
}


class Orch:
    def __init__(self, tool_map=tool_map, tool_schema=tool_schema, state=State, max_retries=8):
        self.tool_map = tool_map
        self.tools = tool_schema
        self.state = state
        self.max_retries = max_retries

    def create(self, prompt):
        self.state.messages.insert(0, {"role": "user", "content": prompt})
        response = generate_doctype_payload_agent(self.state, self.tools)
        message = response.choices.messages[0]
        
        
        for i in range(self.max_retries):
            last_response = self.state.messages[-1]
            if last_response.get("tool_calls", None):
                is_error, results = self.execute_tool_calls(last_response)
                if is_error:
                    response = validate_doctype_payload_agent(self.state, self.tools)
                    self.state.message.append(response)
                else:
                    for result in results:
                        self.state.message.append(result)
                    response = create_doctype_agent(self.state)
                    self.state.message.append(response)
            else:
                return self.state.message[-1]
                

    def execute_tool_calls(self, message):
        tool_calls = message.get("tool_calls", None) or []
        tool_messages = []
        is_error = False
        for tool in tool_calls:
            name = tool.function.name
            args = tool.function.arguments or "{}"

            try:
                parsed_arg = json.loads(args)
            except Exception as e:
                is_error = True
                tool_message = str(e)
                tool_messages.append({
                "role": "function",
                "tool_call_id": tool.id,
                "name": name,
                "content": tool_message,
                })
            
            tool_function = tool_map.get(name)

            if not tool_function:
                is_error = True
                tool_message = f"Tool '{name}' not found in tool map."
                tool_messages.append({
                "role": "function",
                "tool_call_id": tool.id,
                "name": name,
                "content": tool_message,
                })
            else:
                result = tool_function(**args)
                tool_messages.append({
                "role": "function",
                "tool_call_id": tool.id,
                "name": name,
                "content": tool_message,
                })
        return is_error, tool_messages
