"""Subcontractor Service Order controller."""

from __future__ import annotations

from frappe.model.document import Document


class SubcontractorServiceOrder(Document):
    def before_save(self):
        if not self.company:
            from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
            self.company = get_default_company()
