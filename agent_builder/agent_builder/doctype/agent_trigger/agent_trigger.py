# agent_builder/agent_builder/doctype/agent_trigger/agent_trigger.py
import frappe
from frappe.model.document import Document
from frappe.utils import random_string


class AgentTrigger(Document):
	def validate(self):
		if not self.agent_name and not self.workflow_name:
			frappe.throw("Set either 'Agent to Run' or 'Workflow to Run' (at least one is required).")

		if self.agent_name and not self.input_template:
			frappe.throw("Input Template is required when targeting an Agent — it becomes the agent's first message.")

		if self.trigger_type == "Webhook" and not self.webhook_token:
			# Generated once, kept stable across saves (read-only field —
			# the only writer is this validate()).
			self.webhook_token = random_string(32)