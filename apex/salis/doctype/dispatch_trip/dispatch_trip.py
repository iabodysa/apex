# Copyright (c) 2026, afmcoltd
"""Dispatch Trip lifecycle and atomic request assignment.

The ledger insert and its matching delete on cancel pass ``ignore_permissions`` for the subledger
reason: Trip Fulfilment Ledger is an ``in_create`` DocType on which no role holds create or write,
so the controller is the only path a row can take. Granting the dispatcher create would let a
fulfilment row exist with no trip behind it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_time, now_datetime

from apex.apex_core.utils.portal_identity import DRIVER, publish_to_portal_subject
from apex.apex_core.utils.portal_live import notify_doctype
from apex.salis.boarding_engine import reverse_trip_boarding
from apex.salis.doctype.dispatch_trip.trip_manifest import (
    ROUTE_STOP_FIELDS,
    copy_route_stops,
    request_names,
    resolve_route_context,
    sync_passengers,
    validate_request_stop_mappings,
)
from apex.salis.utils import (
    add_timeline_note,
    drive_transport_request,
    validate_vehicle_compliance,
    lock_vehicle,
    revert_transport_request,
)


class DispatchTrip(Document):
    def validate(self):
        """Resolve immutable trip context, then validate execution facts."""
        self._resolve_route_context()
        self._copy_route_stops()
        self._validate_request_stop_mappings()
        self._sync_passengers()
        self._guard_initial_status()
        self._validate_odometer()
        self._validate_trip_times()
        validate_vehicle_compliance(self)
        self._require_completion_notes()
        self._enforce_capacity()

    def _resolve_route_context(self):
        resolve_route_context(self)

    def _copy_route_stops(self):
        copy_route_stops(self)

    def _validate_request_stop_mappings(self):
        validate_request_stop_mappings(self)

    def _request_names(self):
        return request_names(self)

    def _sync_passengers(self):
        sync_passengers(self)

    def _enforce_capacity(self):
        """Reject request groups larger than a known vehicle capacity."""
        if not (self.vehicle and self.assigned_requests):
            return
        capacity = (
            frappe.db.get_value("Salis Vehicle", self.vehicle, "seat_capacity") or 0
        )
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
        """Notify subscribed driver portals after a trip change."""
        self._publish_driver_update()

    def _publish_driver_update(self):
        """Tell authorised desk and portal clients to refetch after commit."""
        try:
            notify_doctype("Dispatch Trip", "driver_trip_update", {"name": self.name})
        except Exception:
            pass
        try:
            if self.driver:
                publish_to_portal_subject(
                    DRIVER, self.driver, "driver_trip_update", {"name": self.name}
                )
        except Exception:
            pass

    def before_submit(self):
        """Blocks submission until the trip has stops, resources, date and riders."""
        self._enforce_dispatch_readiness()

    def _enforce_dispatch_readiness(self):
        """A trip must carry its executable route and resources before submission."""
        required = {
            "vehicle": _("Vehicle"),
            "driver": _("Driver"),
            "trip_date": _("Trip Date"),
            "project": _("Project"),
        }
        for fieldname, label in required.items():
            if not self.get(fieldname):
                frappe.throw(
                    _("Dispatch readiness: {0} is required before submitting.").format(
                        label
                    )
                )

        if not self.stops:
            frappe.throw(
                _("Dispatch readiness: Add at least one trip stop before submitting.")
            )
        self._validate_request_stop_mappings()
        if not self._request_names() and not self.boarding_state:
            frappe.throw(
                _(
                    "Dispatch readiness: Add at least one request or passenger before submitting."
                )
            )

    def _require_completion_notes(self):
        """Completion Notes are mandatory once the trip is marked Completed."""
        if self.status == "Completed" and not (self.completion_notes or "").strip():
            frappe.throw(
                _("Completion Notes are required when the trip status is Completed.")
            )

    def _guard_initial_status(self):
        """Force new trips through the native workflow from Planned."""
        if self.is_new() and self.status and self.status != "Planned":
            frappe.throw(
                _(
                    "A new Dispatch Trip must start as Planned; {0} is reached through the workflow."
                ).format(_(self.status))
            )

    def _validate_odometer(self):
        """Requires odometer start and end to be set together, with end not less than start."""
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
        """Validate recorded same-day execution times at completion."""
        if self.status != "Completed":
            return
        if not (self.depart_time and self.return_time):
            return
        if get_time(self.return_time) < get_time(self.depart_time):
            frappe.throw(_("Return Time cannot be earlier than Depart Time."))

    def on_submit(self):
        """Advances the vehicle's odometer and fulfils the linked transport request once a trip completes."""
        if self.status == "Completed" and self.odometer_end and self.vehicle:
            lock_vehicle(self.vehicle)
            current = (
                frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            )
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

        if self.status == "Completed" and self._request_names():
            self._fulfil_transport_requests()
            self._post_fulfilment_ledger()

    def _fulfil_transport_requests(self):
        """Fulfil every request; any failure aborts the whole transaction."""
        for request in self._request_names():
            drive_transport_request(
                request,
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
        """Write the immutable completion ledger once."""
        if frappe.db.exists("Trip Fulfilment Ledger", {"dispatch_trip": self.name}):
            return
        request_names = self._request_names()
        worker_count = sum(
            row.worker_count or 0
            for row in frappe.get_all(
                "Transport Request",
                filters={"name": ["in", request_names]},
                fields=["worker_count"],
            )
        )
        has_timestamps = 1 if (self.return_time and self.depart_time) else 0
        ledger = frappe.new_doc("Trip Fulfilment Ledger")
        ledger.update(
            {
                "dispatch_trip": self.name,
                "transport_request": self.transport_request
                or (request_names[0] if request_names else None),
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
        ledger.insert(ignore_permissions=True)

    def on_cancel(self):
        """Reverse request and boarding effects; odometer stays monotonic."""
        self._revert_transport_requests()
        for row in frappe.get_all(
            "Trip Fulfilment Ledger",
            filters={"dispatch_trip": self.name},
            pluck="name",
        ):
            frappe.delete_doc(
                "Trip Fulfilment Ledger", row, ignore_permissions=True, force=True
            )
        reverse_trip_boarding(self.name)

    def on_trash(self):
        """Release the requests a draft trip claimed.

        ``assign_requests_to_trip`` stamps ``is_assigned``/``assigned_to_trip``
        while the trip is still a draft, and the re-assignment guard then refuses
        the request to any other trip. Cancellation clears them, but a draft is
        deleted rather than cancelled, so without this the request is locked to a
        trip that no longer exists and no desk field can free it.
        """
        for request in self._request_names():
            frappe.db.set_value(
                "Transport Request",
                request,
                {"is_assigned": 0, "assigned_to_trip": None},
                update_modified=False,
            )

    def _revert_transport_requests(self):
        """Reverse every request still fulfilled by this trip."""
        for request in self._request_names():
            revert_transport_request(
                request,
                from_state="Fulfilled",
                to_state="Scheduled",
                dispatch_trip=self.name,
                clear_fields=[
                    "fulfilled_on",
                    "assigned_vehicle",
                    "assigned_driver",
                    "dispatch_trip",
                    "assigned_to_trip",
                ],
                reset_fields={"is_assigned": 0},
            )


ASSIGNMENT_ROLES = (
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "System Manager",
)

AD_HOC_TRIP_FIELDS = (
    "project",
    "trip_date",
    "planned_start",
    "planned_end",
    "vehicle",
    "driver",
)

AD_HOC_TRIP_SAVEPOINT = "create_ad_hoc_dispatch_trip"


def _request_rider_count(request):
    manifest_count = len(request.get("workers") or []) + len(
        request.get("adhoc_passengers") or []
    )
    return max(
        manifest_count,
        cint(request.get("worker_count")),
        cint(request.get("passenger_count")),
    )


@frappe.whitelist(methods=["POST"])
def create_ad_hoc_trip(trip, transport_requests):
    """Create one ad-hoc trip and attach approved requests in one transaction.

    The caller controls only ad-hoc planning fields and stop facts. Workflow,
    assignment, passenger, and status fields continue through the Dispatch Trip
    controller and ``assign_requests_to_trip`` invariants.
    """
    if not (set(frappe.get_roles()) & set(ASSIGNMENT_ROLES)):
        frappe.throw(
            _("You are not permitted to create ad-hoc dispatch trips."),
            frappe.PermissionError,
        )
    if not frappe.has_permission("Dispatch Trip", "create"):
        frappe.throw(
            _("You do not have permission to create a Dispatch Trip."),
            frappe.PermissionError,
        )

    if isinstance(trip, str):
        trip = frappe.parse_json(trip)
    if not isinstance(trip, dict):
        frappe.throw(_("Trip must be an object."))
    transport_requests = _parse_request_assignment_rows(transport_requests)
    if not transport_requests:
        frappe.throw(_("Add at least one Transport Request to the ad-hoc trip."))

    stops = trip.get("stops") or []
    if isinstance(stops, str):
        stops = frappe.parse_json(stops)
    if not isinstance(stops, list) or not stops:
        frappe.throw(_("Add at least one stop to the ad-hoc trip."))
    if not all(isinstance(row, dict) for row in stops):
        frappe.throw(_("Every trip stop must be an object."))

    payload = {
        "doctype": "Dispatch Trip",
        "trip_type": "Ad Hoc",
        "status": "Planned",
        **{fieldname: trip.get(fieldname) for fieldname in AD_HOC_TRIP_FIELDS},
        "stops": [
            {
                fieldname: row.get(fieldname)
                for fieldname in ROUTE_STOP_FIELDS
                if row.get(fieldname) is not None
            }
            for row in stops
        ],
    }

    frappe.db.savepoint(AD_HOC_TRIP_SAVEPOINT)
    try:
        doc = frappe.get_doc(payload)
        doc.insert()
        assigned = assign_requests_to_trip(doc.name, transport_requests)
    except Exception:
        frappe.db.rollback(save_point=AD_HOC_TRIP_SAVEPOINT)
        raise
    frappe.db.release_savepoint(AD_HOC_TRIP_SAVEPOINT)
    return {"name": doc.name, "assigned_requests": assigned}


@frappe.whitelist(methods=["POST"])
def assign_requests_to_trip(dispatch_trip, transport_requests):
    """Atomically attach requests and their pickup/drop-off stops to one trip."""
    if not (set(frappe.get_roles()) & set(ASSIGNMENT_ROLES)):
        frappe.throw(
            _("You are not permitted to assign transport requests."),
            frappe.PermissionError,
        )

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip, for_update=True)
    if not frappe.has_permission("Dispatch Trip", "write", doc=trip):
        frappe.throw(
            _("You do not have write permission on this Dispatch Trip."),
            frappe.PermissionError,
        )
    if trip.docstatus != 0 or trip.status != "Planned":
        frappe.throw(_("Requests can only be assigned to a Planned trip."))

    rows = _normalise_request_assignments(transport_requests, trip)
    existing = {row.transport_request for row in (trip.assigned_requests or [])}
    requests = []
    for row in rows:
        name = row["transport_request"]
        if not name or name in existing:
            continue

        request = frappe.get_doc("Transport Request", name, for_update=True)
        if not frappe.has_permission("Transport Request", "write", doc=request):
            frappe.throw(
                _("You do not have write permission on Transport Request {0}.").format(
                    name
                ),
                frappe.PermissionError,
            )
        if request.status not in ("Approved", "Scheduled"):
            frappe.throw(
                _("Transport Request {0} must be Approved or Scheduled.").format(name)
            )
        linked_trip = request.assigned_to_trip or request.dispatch_trip
        if linked_trip and linked_trip != trip.name:
            frappe.throw(
                _("Transport Request {0} is already assigned to trip {1}.").format(
                    name, linked_trip
                )
            )
        requests.append(request)

    for request in requests:
        row = next(item for item in rows if item["transport_request"] == request.name)
        trip.append(
            "assigned_requests",
            {
                "transport_request": request.name,
                "pickup_stop": row["pickup_stop"],
                "dropoff_stop": row["dropoff_stop"],
                "requested_count": _request_rider_count(request),
                "purpose": request.transport_purpose,
            },
        )
        existing.add(request.name)
    trip.save()

    assignment_values = {
        "is_assigned": 1,
        "assigned_to_trip": trip.name,
        "assigned_vehicle": trip.vehicle,
        "assigned_driver": trip.driver,
        "dispatch_trip": trip.name,
    }
    for request in requests:
        if request.status == "Approved":
            drive_transport_request(
                request.name,
                action="Schedule",
                target_state="Scheduled",
                extra_fields=assignment_values,
            )
        else:
            frappe.db.set_value("Transport Request", request.name, assignment_values)
    return [row.transport_request for row in (trip.assigned_requests or [])]


def _normalise_request_assignments(value, trip):
    value = _parse_request_assignment_rows(value)

    stop_keys = [row.stop_key for row in (trip.stops or []) if row.stop_key]
    known = set(stop_keys)
    result = []
    seen = {}
    for item in value:
        row = item if isinstance(item, dict) else {"transport_request": item}
        name = row.get("transport_request")
        pickup = row.get("pickup_stop")
        dropoff = row.get("dropoff_stop")
        if not pickup and not dropoff and len(stop_keys) <= 2 and stop_keys:
            pickup, dropoff = stop_keys[0], stop_keys[-1]
        if not name or not pickup or not dropoff:
            frappe.throw(
                _(
                    "Each request needs a Transport Request, Pickup Stop and Drop-off Stop."
                )
            )
        if pickup not in known or dropoff not in known:
            frappe.throw(_("Pickup and drop-off must belong to this trip."))
        mapping = (pickup, dropoff)
        if name in seen:
            if seen[name] != mapping:
                frappe.throw(
                    _("Transport Request {0} has conflicting stop mappings.").format(
                        name
                    )
                )
            continue
        seen[name] = mapping
        result.append(
            {
                "transport_request": name,
                "pickup_stop": pickup,
                "dropoff_stop": dropoff,
            }
        )
    return result


def _parse_request_assignment_rows(value):
    """Parse the request collection before any trip row is inserted.

    ``frappe.parse_json`` (frappe/__init__.py:2491) handles the JSON case, but only
    when the value LOOKS like JSON: the one thing it cannot do is accept a bare
    document name — it raises — so a single request passed as a plain string is
    wrapped rather than parsed. Parsing before any insert is the point: a malformed
    collection must refuse the whole trip, not leave half its rows written.
    """
    if isinstance(value, str):
        value = (
            frappe.parse_json(value)
            if value.strip().startswith(("[", "{"))
            else [value]
        )
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        frappe.throw(_("Transport Requests must be a list."))
    return value
