from .chains_supervised import (
    generate_doctype_payload_agent,
    validate_doctype_payload_agent,
    create_doctype_agent,
    supervisor_agent,
    execute_tool_calls,
)


from ..agent_.tools_plugin import agent_tools
import json
from typing import TypedDict, List, Dict, Any


class State(TypedDict):
    messages: List[Dict[str, Any]]
    tool_messages: List[Dict[str, Any]]
    payload: Dict[str, Any]
    last_error: str | None






AGENT_REGISTRY = {
    "validate_doctype_payload_agent": validate_doctype_payload_agent,
    "create_doctype_agent": create_doctype_agent,
    "generate_doctype_payload_agent": generate_doctype_payload_agent,
    
}


class Orch:
    def __init__(self, max_retries=8):
        self.tools = agent_tools
        self.max_retries = max_retries

        self.state: State = {
            "messages": [],
            "tool_messages": [],
            "payload": {},
            "metadata": [],
            "last_error": None,
        }

    def create(self, prompt: str):
        self.state["messages"].append({"role": "user", "content": prompt})

        response = generate_doctype_payload_agent(self.state, self.tools)
        self.state["messages"].append(response)

        for _ in range(self.max_retries):

            last_msg = self.state["messages"][-1]
            for msg in self.state["messages"]:
                print(f"Message: {msg} ", "\n \n ######################################## \n")
            print(f"Orch iteration {_ + 1}", "\n \n ######################################## \n")

            if "tool_calls" in last_msg:
                print(f"Tool calls detected: {last_msg['tool_calls']}")
                self.state, is_error = execute_tool_calls(self.state, last_msg)
                print(f"Tool execution completed. is_error={is_error} \n,  {self.state['tool_messages'][-1]}", "\n \n ######################################## \n")

                supervisor_response = supervisor_agent(self.state)
                next_step = json.loads(supervisor_response["content"])["next_agent"]
                print(f"Supervisor decided next step: {next_step} \n \n ######################################## \n")

                if next_step == "END":
                    return self.state

                agent_fn = AGENT_REGISTRY[next_step]
                response = agent_fn(self.state, self.tools)
                self.state["messages"].append(response)
            else:
                return last_msg

        return self.state
