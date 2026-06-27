"""Passenger Manifest controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class PassengerManifest(Document):
    def validate(self):
        self._guard_duplicate_passengers()
        self.passenger_count = len(self.passengers or [])

    def _guard_duplicate_passengers(self):
        # A duplicate employee row would inflate passenger_count and the seat headcount.
        seen = set()
        for row in self.passengers or []:
            if not row.employee:
                continue
            if row.employee in seen:
                frappe.throw(
                    _("Employee {0} appears more than once in the passenger list.").format(row.employee)
                )
            seen.add(row.employee)
