# Copyright (c) 2026, Faisal Imali and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# from agent_builder.native_api.agent.setup import invalidate_agent_definition, invalidate_agents_for_skill


class AgentDefinition(Document):
	def validate(self):
		if not self.is_enabled:
			return
		if not self.skill and not self.instructions:
			frappe.throw(
				"An enabled Agent Definition needs either a linked Skill (preferred) or Instructions text.",
				title="Agent has no identity",
			)
		if self.skill and not frappe.db.exists("Skill", self.skill):
			frappe.throw(f"Linked Skill {self.skill} does not exist.")
		if self.skill and not frappe.db.get_value("Skill", self.skill, "is_enabled"):
			frappe.throw(f"Linked Skill {self.skill} is disabled. Enable it first.")

	def on_update(self):
		# Invalidate this agent's cache on any change
		invalidate_agent_definition(self.agent_name)

	def on_trash(self):
		if self.is_default:
			frappe.throw("Cannot delete the default Agent Definition. Unset 'Is Default' first.")
		# Also clear cache
		invalidate_agent_definition(self.agent_name)
