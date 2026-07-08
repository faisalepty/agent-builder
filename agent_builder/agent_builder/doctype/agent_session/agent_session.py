# Copyright (c) 2026, Faisal Imali and contributors
# For license information, please see license.txt

# import frappe
import uuid
from frappe.model.document import Document


class Agentsession(Document):
	_DOCTYPE_NAME = "Agent session"

	def autoname(self):
		"""Generate a unique name for the agent session."""
		self.name = str(uuid.uuid4())