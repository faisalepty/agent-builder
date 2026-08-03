# agent_builder/native_api/tools/workflow_tools/human_approval.py

import json

import frappe

from agent_builder.native_api.tools.decorator import tool


@tool(schema_name="human_approval")
def human_approval(args: dict, **kwargs) -> str:
	"""Pause the enclosing workflow run for a human decision.

	This is a normal, stateless tool like any other — it does not itself
	wait for anything (Frappe tool calls are request/response, not
	long-lived). It fires a notification on the requested channel, then
	returns a pause marker ({"__workflow_pause__": True, ...}) that only
	engine.py's _execute_tool_step understands: it raises WorkflowPaused,
	which the workflow's main loop catches to persist an Agent Workflow
	Run as "Paused" and hand control back to the caller immediately —
	resumed later via resume_workflow(), not by this function blocking.
	"""
	channel = args.get("channel", "Desk")
	message = args.get("message", "Approval requested.")
	approvers = args.get("approvers") or []

	_notify(channel, message, approvers)

	return json.dumps(
		{
			"__workflow_pause__": True,
			"message": message,
			"channel": channel,
			"approvers": approvers,
		}
	)


def _notify(channel: str, message: str, approvers: list):
	recipients = approvers or [frappe.session.user]

	if channel in ("Desk", "Both"):
		for user in recipients:
			try:
				frappe.get_doc(
					{
						"doctype": "Notification Log",
						"for_user": user,
						"type": "Alert",
						"subject": "Approval requested",
						"email_content": message,
					}
				).insert(ignore_permissions=True)
			except Exception:
				frappe.log_error(title="Approval Notify Failed (Desk)", message=frappe.get_traceback())

	if channel in ("Email", "Both"):
		try:
			frappe.sendmail(recipients=recipients, subject="Approval requested", message=message)
		except Exception:
			frappe.log_error(title="Approval Notify Failed (Email)", message=frappe.get_traceback())