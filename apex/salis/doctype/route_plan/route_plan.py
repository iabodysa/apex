# Copyright (c) 2026, AFMCO and contributors
"""Route Plan controller.

Route Plan is a Movement *fulfilment* record for an Operations request.
Operations owns the request and Movement fulfils it: Operations requests a
movement via the Transport Request; Movement plans and fulfils it here. Movement
is consulted, not the approver.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import drive_transport_request, revert_transport_request


class RoutePlan(Document):
    def validate(self):
        for stop in self.stops or []:
            if not stop.stop_name:
                frappe.throw(_("Row {0}: Stop Name is required").format(stop.idx))
        self.total_stops = len(self.stops or [])
        self._default_operations_requester()

    def on_submit(self):
        # [#hi89yj]
        self.db_set("movement_planner", frappe.session.user)
        self._mark_request_scheduled()

    def on_cancel(self):
        # [#p5mqbj]
        if not self.transport_request:
            return
        revert_transport_request(
            self.transport_request,
            from_state="Scheduled",
            to_state="Approved",
            clear_fields=["route_plan"],
        )

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
        """When a Route Plan is submitted against a Transport Request, drive that
        request to Scheduled (via the native workflow "Schedule" transition) and
        stamp the plan back onto it. Terminal requests (already
        Fulfilled/Cancelled) are left untouched by the drive helper."""
        if not self.transport_request:
            return
        drive_transport_request(
            self.transport_request,
            action="Schedule",
            target_state="Scheduled",
            extra_fields={"route_plan": self.name},
        )
