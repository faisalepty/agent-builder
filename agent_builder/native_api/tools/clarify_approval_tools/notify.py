# agent_builder/native_api/notify.py
import frappe

def notify_run_complete(user: str, subject: str, message: str, success: bool = True):
    frappe.publish_realtime(
        "msgprint",
        {
            "message": message,
            "title": subject,
            "indicator": "green" if success else "red",
        },
        user=user,
    )