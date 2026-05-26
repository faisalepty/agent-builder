import frappe
from run_agent import AIAgent


@frappe.whitelist()
def chat(message):
    agent = AIAgent(
        model="anthropic/claude-sonnet-4",
        quiet_mode=True,
    )
    result = agent.run_conversation(user_message=message)
    return {"response": result["final_response"]}