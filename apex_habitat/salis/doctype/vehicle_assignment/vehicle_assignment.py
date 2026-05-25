"""Vehicle Assignment controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class VehicleAssignment(Document):
    def validate(self):
        self._validate_dates()

    def _validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            frappe.throw(_("End Date cannot be earlier than Start Date."))
