"""Route Plan controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

# Transport Request statuses that are terminal and must not be reopened.
_TR_TERMINAL = {"Fulfilled", "Cancelled"}


class RoutePlan(Document):
    def validate(self):
        self.total_stops = len(self.stops or [])

    def on_submit(self):
        self._mark_request_scheduled()

    def _mark_request_scheduled(self):
        """When a Route Plan is submitted against a Transport Request, move that
        request to Scheduled and stamp the plan back onto it. Terminal requests
        (already Fulfilled/Cancelled) are left untouched."""
        if not self.transport_request:
            return
        status = frappe.db.get_value(
            "Transport Request", self.transport_request, "status"
        )
        if status in _TR_TERMINAL:
            return
        frappe.db.set_value(
            "Transport Request",
            self.transport_request,
            {"status": "Scheduled", "route_plan": self.name},
        )
