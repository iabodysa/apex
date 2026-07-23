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

    def set_supervisor_decision(self, decision: str, user: str, reason: str | None = None):
        """Record the Route Supervisor's approval decision on this plan.

        State-machine writer for the ``supervisor_approval`` field. Called only by the
        guarded ``route_supervisor`` portal API after it has verified the caller is the
        assigned supervisor and the plan is still Pending — the permission/precondition
        gate lives there; this method just performs the write atomically.

        ``supervisor_approval`` and its audit fields are ``allow_on_submit``, so the
        decision persists on the already-submitted plan without an amendment. Uses
        ``db_set`` (audit-only stamp, no re-validate) mirroring the driver-portal
        execution stamps. Rejection reason is cleared on approval so a re-approval of a
        previously rejected plan carries no stale reason."""
        if decision not in ("Approved", "Rejected"):
            frappe.throw(_("Unsupported supervisor decision."))
        self.db_set(
            {
                "supervisor_approval": decision,
                "supervisor_action_by": user,
                "supervisor_action_on": frappe.utils.now_datetime(),
                "supervisor_rejection_reason": reason if decision == "Rejected" else None,
            },
            update_modified=False,
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
