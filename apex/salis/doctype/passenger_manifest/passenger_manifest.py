# Copyright (c) 2026, afmcoltd
"""Passenger Manifest controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class PassengerManifest(Document):
    def validate(self):
        """Blocks duplicate passengers and recomputes the passenger count."""
        self._guard_duplicate_passengers()
        self.passenger_count = len(self.passengers or [])

    def _guard_duplicate_passengers(self):
        """Blocks an employee appearing more than once in the passenger list."""
        seen = set()
        for row in self.passengers or []:
            if not row.employee:
                continue
            if row.employee in seen:
                frappe.throw(
                    _("Employee {0} appears more than once in the passenger list.").format(row.employee)
                )
            seen.add(row.employee)
