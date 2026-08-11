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

        Dispatch Trip has no project of its own — every project scope reaches a trip
        through its Route Plan (``dispatch_board._trips_today_pane``, and
        ``permissions.dispatch_trip_query``). So a plan with no project does not degrade
        gracefully: its trips vanish from a scoped supervisor's board entirely while
        staying visible to an unscoped one, which is the worst shape a scoping gap takes.

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
        frappe.publish_realtime(
            "route_plan_decision",
            {"name": self.name, "approval": decision},
            doctype="Route Plan",
            after_commit=True,
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
