"""Dispatch Trip controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from apex_habitat.salis.salis_lib import lock_vehicle, log_activity

# Transport Request statuses that are terminal and must not be reopened.
_TR_TERMINAL = {"Fulfilled", "Cancelled"}

# Allowed forward status transitions. Cancellation is allowed from any state.
_ALLOWED_TRANSITIONS = {
    "Planned": {"Planned", "Dispatched", "Cancelled"},
    "Dispatched": {"Dispatched", "Completed", "Cancelled"},
    "Completed": {"Completed", "Cancelled"},
    "Cancelled": {"Cancelled"},
}


class DispatchTrip(Document):
    def validate(self):
        self._resolve_transport_request()
        self._enforce_status_flow()
        self._validate_odometer()
        self._enforce_compliance()
        self._require_completion_notes()

    def _resolve_transport_request(self):
        """Resolve the Transport Request from the Route Plan when not already set,
        so the fulfilment chain is intact even if the fetch did not populate it."""
        if self.transport_request or not self.route_plan:
            return
        self.transport_request = frappe.db.get_value(
            "Route Plan", self.route_plan, "transport_request"
        )

    def before_submit(self):
        self._enforce_dispatch_readiness()

    def _enforce_dispatch_readiness(self):
        """tiered authorityG50: a trip must be ready before it is submitted."""
        required = {
            "route_plan": _("Route Plan"),
            "vehicle": _("Vehicle"),
            "driver": _("Driver"),
            "trip_date": _("Trip Date"),
        }
        for fieldname, label in required.items():
            if not self.get(fieldname):
                frappe.throw(
                    _("Dispatch readiness: {0} is required before submitting.").format(label)
                )

    def _require_completion_notes(self):
        """Completion Notes are mandatory once the trip is marked Completed."""
        if self.status == "Completed" and not (self.completion_notes or "").strip():
            frappe.throw(
                _("Completion Notes are required when the trip status is Completed.")
            )

    def _enforce_compliance(self):
        """Block (or warn) when the linked vehicle's compliance has expired.

        Reads Salis Vehicle.compliance_status; if Expired, honours the
        Salis Settings.block_assignment_on_expired_compliance flag: block when
        set, otherwise warn. Safe default = warn.
        """
        if not self.vehicle:
            return
        status = frappe.db.get_value("Salis Vehicle", self.vehicle, "compliance_status")
        if status != "Expired":
            return
        if frappe.db.get_single_value(
            "Salis Settings", "block_assignment_on_expired_compliance"
        ):
            frappe.throw(
                _("Vehicle {0} has expired compliance and cannot be dispatched/assigned.").format(
                    self.vehicle
                )
            )
        else:
            frappe.msgprint(
                _("Warning: vehicle {0} has expired compliance.").format(self.vehicle),
                indicator="orange",
            )

    def _enforce_status_flow(self):
        before = self.get_doc_before_save()
        if not before or not before.status:
            return
        old, new = before.status, self.status
        if new == old:
            return
        if new not in _ALLOWED_TRANSITIONS.get(old, set()):
            frappe.throw(
                _("Illegal status change from {0} to {1}.").format(_(old), _(new))
            )

    def _validate_odometer(self):
        if self.odometer_end is not None and self.odometer_start is not None:
            if self.odometer_end < self.odometer_start:
                frappe.throw(
                    _("Trip end odometer ({0}) cannot be less than start ({1}).").format(
                        self.odometer_end, self.odometer_start
                    )
                )

    def on_submit(self):
        if self.status == "Completed" and self.odometer_end and self.vehicle:
            lock_vehicle(self.vehicle)
            current = frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            if self.odometer_end > current:
                frappe.db.set_value(
                    "Salis Vehicle", self.vehicle, "odometer", self.odometer_end
                )
            log_activity(
                action="Trip Completed",
                entity_type="Salis Vehicle",
                entity_name=self.vehicle,
                details={"trip": self.name, "odometer_end": self.odometer_end},
            )

        if self.status == "Completed" and self.transport_request:
            self._fulfil_transport_request()
            self._post_fulfilment_ledger()

    def _fulfil_transport_request(self):
        """Mark the linked Transport Request as Fulfilled and stamp the assignment
        outcome back onto it. Terminal requests are left untouched."""
        status = frappe.db.get_value(
            "Transport Request", self.transport_request, "status"
        )
        if status in _TR_TERMINAL:
            return
        frappe.db.set_value(
            "Transport Request",
            self.transport_request,
            {
                "status": "Fulfilled",
                "fulfilled_on": now_datetime(),
                "assigned_vehicle": self.vehicle,
                "assigned_driver": self.driver,
                "dispatch_trip": self.name,
            },
        )

    def _post_fulfilment_ledger(self):
        """Insert a read-only Trip Fulfilment Ledger row capturing the completed
        trip. System-written audit memo; humans never create these."""
        worker_count = (
            frappe.db.get_value(
                "Transport Request", self.transport_request, "worker_count"
            )
            or 0
        )
        on_time = 1 if (self.return_time and self.depart_time) else 0
        ledger = frappe.new_doc("Trip Fulfilment Ledger")
        ledger.update(
            {
                "dispatch_trip": self.name,
                "transport_request": self.transport_request,
                "route_plan": self.route_plan,
                "vehicle": self.vehicle,
                "driver": self.driver,
                "trip_date": self.trip_date,
                "worker_count": worker_count,
                "on_time": on_time,
                "logged_at": now_datetime(),
            }
        )
        ledger.insert(ignore_permissions=True)  # audit-ok
