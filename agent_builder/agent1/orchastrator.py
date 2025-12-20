from .chains import (
    generate_doctype_payload_agent,
    create_doctype_agent,
    validate_doctype_payload_agent,
    execute_tool_calls,
    route_tool_call,
)
from typing import TypedDict, List
import json
from ..agent_.tools import tool_agent_create, tool_validate_payload
from ..agent_.tools_plugin import agent_tools as tool_schema


class State(TypedDict):
    system_message: str
    messages: List


tool_map = {
    "tool_agent_create": tool_agent_create,
    "tool_validate_payload": tool_validate_payload
}


class Orch:
    def __init__(self, tool_map=tool_map, tool_schema=tool_schema, max_retries=8):
        self.tool_map = tool_map
        self.tools = tool_schema

        # FIX: Initialize an instance, not the TypedDict class
        self.state = {
            "system_message": "",
            "messages": [],
            "tool_messages": [],
            "payload": {}
        }

        self.max_retries = max_retries

    def create(self, prompt):
        # FIX: Correct key name
        self.state["messages"].append({"role": "user", "content": prompt})

        # Call first agent
        response = generate_doctype_payload_agent(self.state, self.tools)
        self.state["messages"].append(response)
        print("Initial response appended: ", response.get("content"), "\n \n TOOLS: \n", response.get("tool_calls"), "\n \n ######################################## \n")

        for _ in range(self.max_retries):
            for msg in self.state["messages"]:
                print(f"Message: {msg} ", "\n \n ######################################## \n")
            print(f"Orch iteration {_ + 1}", "\n \n ######################################## \n")
            last_response = self.state["messages"][-1]
            # If LLM made tool calls
            if last_response.get("tool_calls"):
                print("Executing tool calls...")
                updated_state, is_error, tool_messages = execute_tool_calls(self.state, last_response,)
                self.state = updated_state
                print(f"Tool execution completed. is_error={is_error}, messages={tool_messages}", "\n \n ######################################## \n")
                # Append tool responses
                for msg in tool_messages:
                    self.state["tool_messages"].append(msg)

               
                updated_state, route = route_tool_call(self.state, is_error=is_error)
                self.state = updated_state
                if route == "END":
                    print(f"{last_response}")
                    return 
                print("Routing to: ", route)
                response = route(self.state, self.tools)
                self.state["messages"].append(response)

                # if is_error:
                #     # Retry using validator agent
                #     print("Tool execution had errors, invoking validator agent...")
                #     response = validate_doctype_payload_agent(self.state, self.tools)
                #     print("Validator agent response: ", response.get("content"), "\n", response.get("tool_calls"))
                #     self.state["messages"].append(response)
                # else:
                #     # Tools succeeded → Create doctype
                #     print("Tool execution successful, invoking create agent...")
                #     response = create_doctype_agent(self.state)
                #     print("Create agent response: ", response.get("content"))
                #     self.state["messages"].append(response)
            else:
                return last_response  # Finished

        return self.state["messages"][-1]  # Return whatever we have

    