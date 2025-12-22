# ================================
# orchastrator.py
# ================================

from .chains import (
    supervisor_agent,
    generate_doctype_payload_agent,
    generate_dashboard_chart_payload_agent,
    regenerate_validate_doctype_payload_agent,
    create_doctype_agent,
    execute_tool_calls,
)

from ..agent_.tools_plugin import agent_tools
from typing import TypedDict, Dict, Any, List, Optional
import json


class State(TypedDict):
    messages: List[Dict[str, Any]]
    payload: Dict[str, Any]
    current_agent: str
    validated_payload: Optional[Dict[str, Any]]
    last_tool_result: Optional[Dict[str, Any]]
    last_tool_called: Optional[str]
    has_error: bool
    last_error: Optional[str]
    error_source: Optional[str]
    step_count: int
    max_steps: int


AGENT_REGISTRY = {
    "generate_doctype_payload_agent": generate_doctype_payload_agent,
    "generate_dashboard_chart_payload_agent": generate_dashboard_chart_payload_agent,
    "regenerate_validate_doctype_payload_agent": regenerate_validate_doctype_payload_agent,
    "create_doctype_agent": create_doctype_agent,
}


class Orch:
    def __init__(self, max_steps=10):
        self.tools = agent_tools
        self.max_steps = max_steps

        self.state: State = {
            "messages": [],
            "payload": {},
            "current_agent": None,
            "validated_payload": None,
            "last_tool_result": None,
            "last_tool_called": None,
            "has_error": False,
            "last_error": None,
            "error_source": None,
            "step_count": 0,
            "max_steps": max_steps,
        }

    def create(self, prompt: str, entity: str = "generate_doctype"):
        self.state["messages"].append({"role": "user", "content": prompt})

        
        supervisor_resp = supervisor_agent(self.state)
        print(supervisor_resp)
        decision = json.loads(supervisor_resp["content"])
        next_agent = decision["next_agent"]
        reason = decision["reason"]
        print(f"supervisor agent decided first agent call to: {next_agent} \n with reason: {reason} \n ##################################################")

        response = AGENT_REGISTRY[next_agent](self.state, self.tools)
        print(f"RESPONSE: {response}")
        
        self.state["messages"].append(response)

        while self.state["step_count"] < self.max_steps:
            print(f"{[message for message in self.state['messages']]}")
            self.state["step_count"] += 1

            last_msg = self.state["messages"][-1]

            if "tool_calls" in last_msg:
                print(f"Executing tool: {last_msg['tool_calls']} \n ######################################## \n")
                self.state, _ = execute_tool_calls(self.state, last_msg)
                self.state["messages"].append({
                    "role": "tool",
                    "tool_call_id": last_msg["tool_calls"][0]["id"],
                    "name": last_msg["tool_calls"][0]["function"]["name"],
                    "content": json.dumps(self.state.get("last_tool_result", {"status": "error"}))
                })
                print(f"executing tool call result: \n {self.state['last_tool_result']} \n ##############################################")

                supervisor_resp = supervisor_agent(self.state)

                decision = json.loads(supervisor_resp["content"])
                next_agent = decision["next_agent"]
                self.state["current_agent"] = next_agent    
                print(f"supervisor agent decided first agent call to: {next_agent} \n with reason: {reason} \n ##################################################")

                if next_agent == "END":
                    return self.state

                response = AGENT_REGISTRY[next_agent](self.state, self.tools)
                print(f"RESPONSE: {response}")
                self.state["messages"].append(response)

            
            else:
                return self.state

        return self.state