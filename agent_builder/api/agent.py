# agent_builder/agent_builder/api/agent.py
import frappe
import threading

from frappe.realtime import emit_via_redis, get_user_room
from run_agent import AIAgent


@frappe.whitelist()
def chat(message, session_id=None):
    user = frappe.session.user
    site = frappe.local.site
    room = get_user_room(user)

    def publish(event, data):
        emit_via_redis(event, data, room)

    def on_token(delta):
        publish("agent_token", {"delta": delta})

    def on_tool_start(tool_name, args):
        publish("agent_event", {"type": "tool_start", "tool": tool_name, "args": str(args)})

    def on_tool_done(tool_name, result):
        publish("agent_event", {"type": "tool_done", "tool": tool_name, "result": str(result)[:300]})

    def on_tool_status(tool_name, status):
        publish("agent_event", {"type": "tool_progress", "tool": tool_name, "status": status})

    def run():
        frappe.init(site=site)
        frappe.connect()
        try:
            agent = AIAgent(
                model="openai/gpt-oss-120b:free",
                quiet_mode=False,
                platform="frappe",
                enabled_toolsets=["frappe_tools"],   # platform default + your plugin
                ephemeral_system_prompt=(
                    "You are a Frappe/ERPNext assistant with access to Frappe CRUD tools. "
                    "Before calling any frappe_ tool, always load and follow the frappe-tools skill: "
                    "use skill_view('frappe_tools:frappe-tools'). "
                    "Never deviate from the exact tool names and parameters defined in that skill."
                ),
                # disabled_toolsets=["terminal"],
                stream_delta_callback=on_token,
                tool_start_callback=on_tool_start,
                tool_complete_callback=on_tool_done,
                tool_progress_callback=on_tool_status,
            )
            result = agent.run_conversation(user_message=message)
            publish("agent_done", {"response": result["final_response"]})
        except Exception as e:
            publish("agent_done", {"response": f"Error: {str(e)}"})
        finally:
            frappe.destroy()

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}