"""Dispatch Trip controller.

The FINAL status DocType on the Salis Workflow Spine. Status transitions are
owned by the native **Dispatch Trip Workflow** (see
``salis/workflow/dispatch_trip_workflow/``), not by this controller. The
workflow enforces the role per transition (operational, role-gated — a dispatch
trip carries no maker/checker actor field, so there is no self-approval gate)
and the legal order of states via its transitions:

    Planned (0) --Dispatch--> Dispatched (0) --Complete--> Completed (1)
                                                Completed (1) --Cancel--> Cancelled (2)

``Complete`` is the submit transition (docstatus 0 -> 1): it is the only point
at which the trip's side-effects fire — it locks the vehicle, advances the
odometer, drives the linked Transport Request to Fulfilled through *its* native
workflow, and posts the Trip Fulfilment Ledger. ``Cancel`` (only from the
submitted ``Completed`` state, docstatus 1 -> 2) fires the ``on_cancel``
reversal of those effects. A not-yet-completed (draft) trip that is called off
is simply deleted — it never reached submit and has no downstream effects to
reverse, so it never needs a ``Cancelled`` state (mirroring Fuel Request, which
likewise reserves Cancel for its submitted states). A draft->Cancelled
transition is in any case forbidden by Frappe (cannot cancel before submitting).

This controller keeps only what the workflow cannot express: the dispatch
readiness gate, the Completed completion-notes requirement, the odometer and
compliance validation, the initial-status guard (a trip must be created at
Planned), the idempotent cross-document fulfilment side-effects and their
reversal on cancel.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from apex_habitat.salis.salis_lib import (
    add_timeline_note,
    drive_transport_request,
    lock_vehicle,
    revert_transport_request,
)


class DispatchTrip(Document):
    def validate(self):
        self._resolve_transport_request()
        self._guard_initial_status()
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
        """A trip must be ready (route, vehicle, driver set) before it is submitted."""
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

    def _guard_initial_status(self):
        """A new trip may only be created in the initial state (Planned). Later
        states are reached only through the Dispatch Trip Workflow, which the desk
        drives — this closes the insert-bypass the workflow itself cannot cover
        (a brand-new document inserted directly at a later/terminal status)."""
        if self.is_new() and self.status and self.status != "Planned":
            frappe.throw(
                _("A new Dispatch Trip must start as Planned; {0} is reached through the workflow.").format(
                    _(self.status)
                )
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
            add_timeline_note(
                "Salis Vehicle",
                self.vehicle,
                _("Trip {0} completed; odometer {1}.").format(
                    self.name, self.odometer_end
                ),
            )

        if self.status == "Completed" and self.transport_request:
            self._fulfil_transport_request()
            self._post_fulfilment_ledger()

    def _fulfil_transport_request(self):
        """Drive the linked Transport Request to Fulfilled (via the native workflow
        "Confirm Fulfilment" transition) and stamp the assignment outcome back onto
        it. Terminal requests are left untouched by the drive helper."""
        drive_transport_request(
            self.transport_request,
            action="Confirm Fulfilment",
            target_state="Fulfilled",
            extra_fields={
                "fulfilled_on": now_datetime(),
                "assigned_vehicle": self.vehicle,
                "assigned_driver": self.driver,
                "dispatch_trip": self.name,
            },
        )

    def _post_fulfilment_ledger(self):
        """Insert a read-only Trip Fulfilment Ledger row capturing the completed
        trip. System-written audit memo; humans never create these."""
        if frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": self.name}):
            return
        worker_count = (
            frappe.db.get_value(
                "Transport Request", self.transport_request, "worker_count"
            )
            or 0
        )
        # Data-completeness flag only: records whether the trip captured both a
        # depart and a return timestamp. This is NOT a punctuality measure — the
        # schema carries no planned/scheduled return time to compare against, so
        # an honest "on-time" KPI cannot be computed here.
        has_timestamps = 1 if (self.return_time and self.depart_time) else 0
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
                "has_timestamps": has_timestamps,
                "logged_at": now_datetime(),
                "source_doctype": "Dispatch Trip",
                "source_name": self.name,
            }
        )
        ledger.insert(ignore_permissions=True)  # audit-ok

    def on_cancel(self):
        """Reverse the on_submit fulfilment effects so a cancelled trip does not
        leave the Transport Request permanently Fulfilled or double-count the
        Trip Fulfilment Ledger. Odometer is monotonic and is intentionally not
        rolled back."""
        if self.transport_request:
            # Workflows are forward-only; a cancelled fulfilment is reverted via a
            # guarded system reversal (Fulfilled -> Scheduled), consistent with the
            # workflow's state -> docstatus map.
            revert_transport_request(
                self.transport_request,
                from_state="Fulfilled",
                to_state="Scheduled",
                dispatch_trip=self.name,
                clear_fields=[
                    "fulfilled_on",
                    "assigned_vehicle",
                    "assigned_driver",
                    "dispatch_trip",
                ],
            )
        for row in frappe.get_all(
            "Trip Fulfilment Ledger",
            filters={"dispatch_trip": self.name},
            pluck="name",
        ):
            frappe.delete_doc(
                "Trip Fulfilment Ledger", row, ignore_permissions=True, force=True  # audit-ok
            )
        # Cancellation is recorded natively (Version track_changes + auto-comment).
