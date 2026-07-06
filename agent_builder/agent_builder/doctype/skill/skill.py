import json

import frappe
from frappe import _
from frappe.model.document import Document

MAX_DESCRIPTION_LENGTH = 1024
MAX_PARENT_CHAIN_DEPTH = 50


class Skill(Document):
    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------
    def autoname(self):
        """
        Top-level skills: named directly (admin sets `name` before insert,
        e.g. "business-pulse") — curated by humans, low collision risk.

        Nested skills (parent_skill set): name is derived as
        "{parent_skill}-{reference_slug}" so two different parent skills
        can each have a reference called e.g. "installation" without
        colliding on a flat, global docname.
        """
        if self.parent_skill:
            if not self.reference_slug:
                frappe.throw(_("Reference Slug is required for skills with a Parent Skill"))
            self.name = f"{self.parent_skill}-{frappe.scrub(self.reference_slug)}"
        else:
            self.name = frappe.scrub(self.name_)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self):
        self.validate_no_cycle()
        self.validate_description()
        self.validate_metadata()

    def validate_no_cycle(self):
        if not self.parent_skill:
            return

        if self.parent_skill == self.name:
            frappe.throw(_("A skill cannot be its own parent"))

        seen = {self.name} if self.name else set()
        current = self.parent_skill
        depth = 0

        while current:
            if current in seen:
                frappe.throw(
                    _("Circular parent_skill reference detected involving '{0}'").format(current)
                )
            seen.add(current)
            current = frappe.db.get_value("Skill", current, "parent_skill")
            depth += 1
            if depth > MAX_PARENT_CHAIN_DEPTH:
                frappe.throw(_("parent_skill chain too deep — check for misconfiguration"))

    def validate_description(self):
        if not self.description:
            return
        if "\n" in self.description or "\r" in self.description:
            frappe.throw(
                _(
                    "Description must be a single line. Multi-line descriptions "
                    "silently break skill discovery in the eager index."
                )
            )
        if len(self.description) > MAX_DESCRIPTION_LENGTH:
            frappe.throw(
                _("Description must be {0} characters or fewer").format(MAX_DESCRIPTION_LENGTH)
            )

    def validate_metadata(self):
        if not self.metadata:
            return
        value = self.metadata
        if isinstance(value, str):
            try:
                json.loads(value)
            except (TypeError, ValueError):
                frappe.throw(_("Metadata must be valid JSON"))

    # ------------------------------------------------------------------
    # File privacy enforcement
    # ------------------------------------------------------------------
    def before_save(self):
        self.ensure_attachment_is_private()

    def ensure_attachment_is_private(self):
        if not self.attach:
            return
        file_doc = frappe.db.get_value(
            "File", {"file_url": self.attach}, ["name", "is_private"], as_dict=True
        )
        if file_doc and not file_doc.is_private:
            frappe.db.set_value("File", file_doc.name, "is_private", 1)