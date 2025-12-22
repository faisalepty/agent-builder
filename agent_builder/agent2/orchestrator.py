import json
import frappe
from typing import TypedDict, Dict, Any, List, Optional
from .chains import (
    supervisor_agent,
    generate_doctype_payload_agent,
    generate_dashboard_chart_payload_agent,
    regenerate_validate_doctype_payload_agent,
    create_doctype_agent,
    execute_tool_calls,
)
from ..agent_.tools_plugin import agent_tools

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

    def emit_status(self, text, status="progress"):
        """Sends a message to the Desk UI via Socket.io"""
        frappe.publish_realtime(
            event='agent_builder_msg',
            message={
                'text': text,
                'status': status,
                'agent': self.state.get("current_agent") or "Supervisor"
            },
            user=frappe.session.user
        )

    def create(self, prompt: str):
        self.state["messages"].append({"role": "user", "content": prompt})
        self.emit_status("Initializing AI Orchestrator...", status="progress")
        
        while self.state["step_count"] < self.max_steps:
            self.state["step_count"] += 1
            
            # 2. SUPERVISOR DECISION
            supervisor_resp = supervisor_agent(self.state)
            try:
                # Handle cases where LLM might return a string or dict
                content = supervisor_resp.get("content") if isinstance(supervisor_resp, dict) else supervisor_resp.content
                decision = json.loads(content)
            except Exception as e:
                self.emit_status(f"Decision Error: {str(e)}", status="error")
                return self.state

            next_agent = decision.get("next_agent")
            if next_agent == "END" or next_agent == "null":
                self.emit_status(f"{decision.get("reason")}.", status="success")
                return self.state

            # 4. AGENT EXECUTION
            self.state["current_agent"] = next_agent
            friendly_name = next_agent.replace('_', ' ').title().replace('Agent', '')
            self.emit_status(f"Working: {friendly_name}...", status="progress")

            response = AGENT_REGISTRY[next_agent](self.state, self.tools)
            
            # 5. RESILIENT TOOL CALL HANDLING
            # Check if response has tool_calls attribute (OpenAI style) or dictionary key
            tool_calls = getattr(response, 'tool_calls', None) or response.get('tool_calls')
            
            if tool_calls:
                for tool in tool_calls:
                    # Handle both object-based and dict-based tool calls
                    t_name = tool.function.name if hasattr(tool, 'function') else tool['function']['name']
                    t_id = tool.id if hasattr(tool, 'id') else tool['id']
                    
                    self.emit_status(f"Running Tool: {t_name}...", status="progress")
                    
                    # Update State
                    self.state, _ = execute_tool_calls(self.state, response)
                    
                    # Safe check for result
                    last_res = self.state.get("last_tool_result") or {"status": "error", "message": "No result"}
                    
                    self.state["messages"].append({
                        "role": "tool",
                        "tool_call_id": t_id,
                        "name": t_name,
                        "content": json.dumps(last_res)
                    })
                    
                    if last_res.get("status") == "ok":
                        self.emit_status(f"Verified: {t_name}", status="progress")
                    else:
                        self.emit_status(f"Tool issue: {self.state["last_error"]}", status="progress")
            else:
                self.state["messages"].append(response)

        self.emit_status("Build halted: Maximum steps reached.", status="error")
        return self.state
    

@frappe.whitelist()
def execute_orch(prompt):
    orchestrator = Orch()
    orchestrator.create(prompt)