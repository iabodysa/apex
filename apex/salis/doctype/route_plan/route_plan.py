# Copyright (c) 2026, afmcoltd

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
        self._require_project_on_a_new_plan()

    def _require_project_on_a_new_plan(self):
        if self.is_new() and not self.project:
            frappe.throw(
                _("A route plan must name its project, or its trips are invisible to every project-scoped supervisor.")
            )

    def on_submit(self):
        self.db_set("movement_planner", frappe.session.user)
        self._mark_request_scheduled()

    def on_cancel(self):
        if not self.transport_request:
            return
        revert_transport_request(
            self.transport_request,
            from_state="Scheduled",
            to_state="Approved",
            clear_fields=["route_plan"],
        )

    def _default_operations_requester(self):
        if self.requested_by_operations or not self.transport_request:
            return
        requested_by = frappe.db.get_value(
            "Transport Request", self.transport_request, "requested_by"
        )
        if requested_by:
            self.requested_by_operations = requested_by

    def _mark_request_scheduled(self):
        if not self.transport_request:
            return
        drive_transport_request(
            self.transport_request,
            action="Schedule",
            target_state="Scheduled",
            extra_fields={"route_plan": self.name},
        )
