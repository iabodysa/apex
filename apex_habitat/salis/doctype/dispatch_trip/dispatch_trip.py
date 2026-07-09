# Copyright (c) 2026, AFMCO and contributors
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
from frappe.utils import get_time, now_datetime

from apex_habitat.salis.utils import (
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
        self._validate_trip_times()
        self._enforce_compliance()
        self._require_completion_notes()
        self._enforce_capacity()

    def _resolve_transport_request(self):
        """Resolve the Transport Request from the Route Plan when not already set,
        so the fulfilment chain is intact even if the fetch did not populate it."""
        if self.transport_request or not self.route_plan:
            return
        self.transport_request = frappe.db.get_value(
            "Route Plan", self.route_plan, "transport_request"
        )

    def _enforce_capacity(self):
        """Cap the assigned requests' total workers at the vehicle's seat capacity.

        Preliminary assignment guard: when the vehicle has a known seat_capacity
        (non-zero) and assigned_requests are set, the sum of the requests' worker
        counts must not exceed it. Skipped when capacity is unknown (0/unset) — the
        field is optional and the existing Route Plan path carries no capacity."""
        if not (self.vehicle and self.assigned_requests):
            return
        capacity = frappe.db.get_value("Salis Vehicle", self.vehicle, "seat_capacity") or 0
        if capacity <= 0:
            return
        total = sum((row.requested_count or 0) for row in self.assigned_requests)
        if total > capacity:
            frappe.throw(
                _(
                    "Assigned requests need {0} seats but vehicle {1} seats only {2}."
                ).format(total, self.vehicle, capacity)
            )

    def on_update(self):
        self._publish_driver_update()
        self._mark_assigned_requests()

    def _publish_driver_update(self):
        """Signal subscribed drivers' portals to refetch their trips ahead of a
        manual refresh, on any trip change (assignment / status / board). Routed to
        the Dispatch Trip doctype room; the socket server delivers only to recipients
        with read permission, and each driver's my_trips query is server-scoped to
        their own trips, so scope is honoured. after_commit so subscribers read
        committed state. The payload is advisory — the SPA refetches, it does not
        trust the body. Best-effort: a publish failure must never abort the save."""
        try:
            frappe.publish_realtime(
                "driver_trip_update",
                {"name": self.name},
                doctype="Dispatch Trip",
                after_commit=True,
            )
        except Exception:
            pass

    def _mark_assigned_requests(self):
        """Best-effort: flag each assigned Transport Request as Assigned to this trip.

        Sets the request's is_assigned flag + assigned_to_trip back-link so the
        preliminary assignment is visible on the request, WITHOUT touching the
        workflow-owned status (a native Workflow is forward-only and has no
        "Assigned" state between Scheduled and Fulfilled; forcing one would break
        the existing fulfilment chain). A terminal/cancelled request is skipped.
        Swallowed per row so an un-writable request never aborts the trip save."""
        for row in self.assigned_requests or []:
            if not row.transport_request:
                continue
            try:
                current = frappe.db.get_value(
                    "Transport Request",
                    row.transport_request,
                    ["is_assigned", "assigned_to_trip", "status"],
                    as_dict=True,
                )
                if not current or current.status in ("Cancelled", "Rejected"):
                    continue
                if current.is_assigned and current.assigned_to_trip == self.name:
                    continue
                frappe.db.set_value(
                    "Transport Request",
                    row.transport_request,
                    {"is_assigned": 1, "assigned_to_trip": self.name},
                    update_modified=False,
                )
            except Exception:
                continue

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

        if not self.transport_request and not self.assigned_requests:
            frappe.throw(
                _("Dispatch readiness: A trip must have at least one assigned worker/request before submitting.")
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
        # Both-or-neither: a lone start or lone end reading is incomplete and would
        # silently break distance/odometer-advance accounting on submit.
        # Frappe stores empty Int fields as 0 in MySQL, so treat 0 as «not set».
        start_set = bool(self.odometer_start)
        end_set = bool(self.odometer_end)
        if start_set != end_set:
            frappe.throw(
                _("Odometer start and end must be set together, or both left empty.")
            )
        if start_set and end_set and self.odometer_end < self.odometer_start:
            frappe.throw(
                _("Trip end odometer ({0}) cannot be less than start ({1}).").format(
                    self.odometer_end, self.odometer_start
                )
            )

    def _validate_trip_times(self):
        """Return Time must not precede Depart Time (a single-day trip cannot return
        before it departs).

        Guard to Completed trips only with BOTH times set. A return is a recorded
        execution fact, not a plan, so it is meaningful only at completion. This also
        avoids a false positive on a freshly created Planned trip: Frappe auto-fills
        an unset Time field with the creation-time nowtime (model.create_new), so a
        brand-new trip carries a spurious return_time that can read as earlier than a
        later depart_time depending on the wall-clock at creation. Equal times are
        allowed (a zero-duration record is not a sequencing error). get_time
        normalizes both representations (HH:MM[:SS] str / datetime.time / DB
        timedelta) so the comparison never raises on mismatched types.
        """
        if self.status != "Completed":
            return
        if not (self.depart_time and self.return_time):
            return
        if get_time(self.return_time) < get_time(self.depart_time):
            frappe.throw(_("Return Time cannot be earlier than Depart Time."))

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
        # [#dtn16g]
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
            # [#obmit8]
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
        # Reverse-not-delete the immutable per-worker boarding outcomes: post a
        # negative mirror + flag the originals is_cancelled, so reports net out
        # the cancelled trip while the audit record is preserved.
        from apex_habitat.salis.boarding_engine import reverse_trip_boarding

        reverse_trip_boarding(self.name)
        # [#r7e254]


# Roles permitted to assign requests onto a trip (the transport-supervisor action).
ASSIGNMENT_ROLES = ("Fleet Manager", "Fleet Project Manager", "Fleet Supervisor", "System Manager")


@frappe.whitelist(methods=["POST"])
def assign_requests_to_trip(dispatch_trip, transport_requests):
    """Assign one-or-many Transport Requests onto a Dispatch Trip (supervisor action).

    The preliminary assignment endpoint: appends each request to the trip's
    assigned_requests child table (skipping duplicates) and saves, so the trip
    manifest becomes the union of the assigned requests' workers and the capacity
    guard runs. ``transport_requests`` is a request name or a JSON list of names.

    Authorization (whitelisting is exposure, not authorization): the caller must
    hold a transport-supervisor role AND write permission on this Dispatch Trip
    (frappe.has_permission re-applies DocPerm + per-doc has_permission + User
    Permission scoping). Returns the trip's resulting assigned-request names."""
    if not (set(frappe.get_roles()) & set(ASSIGNMENT_ROLES)):
        frappe.throw(
            _("You are not permitted to assign transport requests."), frappe.PermissionError
        )

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    if not frappe.has_permission("Dispatch Trip", "write", doc=trip):
        frappe.throw(
            _("You do not have write permission on this Dispatch Trip."),
            frappe.PermissionError,
        )

    if isinstance(transport_requests, str):
        transport_requests = (
            frappe.parse_json(transport_requests)
            if transport_requests.strip().startswith("[")
            else [transport_requests]
        )

    existing = {row.transport_request for row in (trip.assigned_requests or [])}
    for request in transport_requests:
        if not request or request in existing:
            continue
        if not frappe.db.exists("Transport Request", request):
            frappe.throw(_("Transport Request {0} does not exist.").format(request))
        trip.append("assigned_requests", {"transport_request": request})
        existing.add(request)
    trip.save()
    return [row.transport_request for row in (trip.assigned_requests or [])]
