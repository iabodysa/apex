"""Route Plan controller.

Route Plan is a Movement *fulfilment* record for an Operations request.
Operations owns the request and Movement fulfils it: Operations requests a
movement via the Transport Request; Movement plans and fulfils it here. Movement
is consulted, not the approver.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

# Transport Request statuses that are terminal and must not be reopened.
_TR_TERMINAL = {"Fulfilled", "Cancelled"}


class RoutePlan(Document):
    def validate(self):
        self.total_stops = len(self.stops or [])
        self._default_operations_requester()

    def on_submit(self):
        self.fulfilled_by_movement = frappe.session.user
        self._mark_request_scheduled()

    def _default_operations_requester(self):
        """Carry the Operations requester from the linked Transport Request
        (Operations owns the request) when not already set."""
        if self.requested_by_operations or not self.transport_request:
            return
        requested_by = frappe.db.get_value(
            "Transport Request", self.transport_request, "requested_by"
        )
        if requested_by:
            self.requested_by_operations = requested_by

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
