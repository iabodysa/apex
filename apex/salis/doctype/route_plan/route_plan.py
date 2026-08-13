# Copyright (c) 2026, afmcoltd
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
        """Requires every stop to have a name, recomputes the stop count, and defaults the requester."""
        for stop in self.stops or []:
            if not stop.stop_name:
                frappe.throw(_("Row {0}: Stop Name is required").format(stop.idx))
        self.total_stops = len(self.stops or [])
        self._default_operations_requester()
        self._require_project_on_a_new_plan()

    def _require_project_on_a_new_plan(self):
        """A NEW plan must name its project. Existing untagged ones are left alone.

        Historical Dispatch Trips may still reach their project through this record.
        New trips store project directly, but a new legacy plan must remain scoped too.

        The field is not marked ``reqd`` because 169 plans already exist without one and a
        blanket rule would refuse to save any of them until somebody invented a project for
        it — a decision about live data, not about the schema. Enforcing it on insert only
        stops the bleeding without freezing history; tagging the existing ones stays an
        operator decision, and the count is what makes it visible.
        """
        if self.is_new() and not self.project:
            frappe.throw(
                _("A route plan must name its project, or its trips are invisible to every project-scoped supervisor.")
            )

    def on_submit(self):
        """Stamps the submitting user as movement planner and drives the linked request to Scheduled."""
        self.db_set("movement_planner", frappe.session.user)
        self._mark_request_scheduled()

    def on_cancel(self):
        """Reverts the linked transport request from Scheduled back to Approved."""
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
