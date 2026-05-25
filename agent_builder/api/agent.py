import frappe
import threading
from run_agent import AIAgent


@frappe.whitelist()
def chat(message, session_id=None):
    user = frappe.session.user

    def on_token(delta):
        frappe.publish_realtime(
            "agent_token",
            {"delta": delta},
            user=user
        )

    def on_tool_start(tool_name, args):
        frappe.publish_realtime(
            "agent_event",
            {"type": "tool_start", "tool": tool_name, "args": str(args)},
            user=user
        )

    def on_tool_done(tool_name, result):
        frappe.publish_realtime(
            "agent_event",
            {"type": "tool_done", "tool": tool_name, "result": str(result)[:300]},
            user=user
        )

    def on_tool_status(tool_name, status):
        frappe.publish_realtime(
            "agent_event",
            {"type": "tool_progress", "tool": tool_name, "status": status},
            user=user
        )

    def run():
        agent = AIAgent(
            model="openai/gpt-oss-120b:free",
            quiet_mode=True,
            disabled_toolsets=["terminal"],
            stream_delta_callback=on_token,
            tool_start_callback=on_tool_start,
            tool_complete_callback=on_tool_done,
            tool_progress_callback=on_tool_status,
        )
        result = agent.run_conversation(user_message=message)
        frappe.publish_realtime(
            "agent_done",
            {"response": result["final_response"]},
            user=user
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started"}