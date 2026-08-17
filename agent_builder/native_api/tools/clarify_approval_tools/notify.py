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
        now=True,
    )

def notify_progress(user: str, message: str, run_id: str = None):
    """Lightweight, ephemeral progress ping — fire-and-forget, never lets
    a notification failure interrupt the actual run."""
    try:
        frappe.publish_realtime(
            "agent_builder_progress",
            {"message": message, "run_id": run_id},
            user=user,
            now=True
        )
    except Exception:
        # Progress is best-effort; never let this take down a step or run.
        frappe.log_error("agent_builder progress emit failed", frappe.get_traceback())