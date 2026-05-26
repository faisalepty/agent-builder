import os
import frappe
import threading

from frappe.realtime import emit_via_redis, get_user_room
from run_agent import AIAgent


# Point Hermes at the app's hermes directory — works on any machine
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HERMES_HOME", os.path.join(_APP_DIR, "hermes"))
os.environ.setdefault("OPENROUTER_API_KEY", "your-key-here")


@frappe.whitelist()
def chat(message, session_id=None):
    user = frappe.session.user
    site = frappe.local.site
    room = get_user_room(user)
    import sys
    print(f"APP_DIR: {_APP_DIR}", file=sys.stderr)
    print(f"HERMES_HOME: {os.environ.get('HERMES_HOME')}", file=sys.stderr)
    print(f"_APP_DIR: {_APP_DIR}", file=sys.stderr)
    sys.exit(0)

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
        try:
            agent = AIAgent(
                model="openai/gpt-oss-120b:free",
                quiet_mode=False,
                disabled_toolsets=["terminal"],
                enabled_toolsets=["frappe"],
                stream_delta_callback=on_token,
                tool_start_callback=on_tool_start,
                tool_complete_callback=on_tool_done,
                tool_progress_callback=on_tool_status,
            )
            result = agent.run_conversation(user_message=message)
            print("Agent final response:", result["final_response"])
            publish("agent_done", {"response": result["final_response"]})
        except Exception as e:
            publish("agent_done", {"response": f"Error: {str(e)}"})
        finally:
            frappe.destroy()

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}