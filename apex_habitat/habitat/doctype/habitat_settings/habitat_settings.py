"""Habitat Settings controller.

Single DocType holding global integration toggles. All defaults are
conservative: no financial posting unless explicitly enabled.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class HabitatSettings(Document):
    def before_save(self):
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            frappe.throw("Only System Manager can modify Habitat Settings.")

        if self.enable_housing_allowance_deduction and self.has_value_changed(
            "enable_housing_allowance_deduction"
        ):
            if not self.authorized_by:
                frappe.throw("Authorized By is required to enable housing allowance deduction.")
            if not self.authorization_document:
                frappe.throw("Authorization Document is required to enable housing allowance deduction.")
            if not self.deduction_activation_date:
                self.deduction_activation_date = frappe.utils.today()

        roles = frappe.get_roles(frappe.session.user)
        self.last_modified_by_role = roles[0] if roles else ""


def get_settings() -> Document:
    """Return the Habitat Settings single document."""
    return frappe.get_single("Habitat Settings")
