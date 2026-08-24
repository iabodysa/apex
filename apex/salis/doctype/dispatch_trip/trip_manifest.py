# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _


ROUTE_STOP_FIELDS = (
    "stop_key",
    "stop_name",
    "accommodation_building",
    "location",
    "planned_time",
    "passengers",
    "latitude",
    "longitude",
)

BOARDING_STATE_FIELDS = (
    "status",
    "confirm_source",
    "notify_count",
    "notify_at",
    "worker_claim_at",
    "reject_count",
    "wait_count",
    "wait_at",
)


def resolve_route_context(trip):
    label = None
    if trip.route_assignment:
        assignment = frappe.db.get_value(
            "Route Assignment",
            trip.route_assignment,
            [
                "route_template",
                "project",
                "driver",
                "vehicle",
                "shift_name",
                "assignment_name",
            ],
            as_dict=True,
        )
        if assignment:
            for fieldname in (
                "route_template",
                "project",
                "driver",
                "vehicle",
                "shift_name",
            ):
                if not trip.get(fieldname):
                    trip.set(fieldname, assignment.get(fieldname))
            label = assignment.get("assignment_name")

    if trip.route_plan:
        plan = frappe.db.get_value(
            "Route Plan",
            trip.route_plan,
            [
                "route_name",
                "transport_request",
                "route_assignment",
                "project",
                "driver",
                "vehicle",
                "shift",
            ],
            as_dict=True,
        )
        if plan:
            legacy_fields = {
                "transport_request": "transport_request",
                "route_assignment": "route_assignment",
                "project": "project",
                "driver": "driver",
                "vehicle": "vehicle",
                "shift_name": "shift",
            }
            for target, source in legacy_fields.items():
                if not trip.get(target):
                    trip.set(target, plan.get(source))
            label = label or plan.get("route_name")

    label = label or trip.route_template or trip.route_plan or _("Trip")
    if trip.trip_date:
        label = _("{0} · {1}").format(label, trip.trip_date)
    trip.trip_title = str(label)[:140]


def copy_route_stops(trip):
    if trip.stops:
        return
    parent = trip.route_template or trip.route_plan
    if not parent:
        return
    parenttype = "Route Template" if trip.route_template else "Route Plan"
    for index, stop in enumerate(
        frappe.get_all(
            "Route Stop",
            filters={"parent": parent, "parenttype": parenttype},
            fields=list(ROUTE_STOP_FIELDS),
            order_by="idx asc",
        ),
        start=1,
    ):
        values = {fieldname: stop.get(fieldname) for fieldname in ROUTE_STOP_FIELDS}
        values["stop_key"] = values.get("stop_key") or f"stop-{index}"
        trip.append("stops", values)


def validate_request_stop_mappings(trip):
    stop_keys = {
        row.get("stop_key") for row in (trip.stops or []) if row.get("stop_key")
    }
    for row in trip.assigned_requests or []:
        if not row.get("pickup_stop") or not row.get("dropoff_stop"):
            if trip.route_plan:
                continue
            frappe.throw(
                _("Request {0} needs pickup and drop-off stops.").format(
                    row.transport_request
                )
            )
        for fieldname, label in (
            ("pickup_stop", _("Pickup Stop")),
            ("dropoff_stop", _("Drop-off Stop")),
        ):
            if row.get(fieldname) not in stop_keys:
                frappe.throw(
                    _("{0} {1} is not a stop on this trip.").format(
                        label, row.get(fieldname)
                    )
                )


def request_names(trip):
    return list(
        dict.fromkeys(
            name
            for name in [
                trip.transport_request,
                *(row.transport_request for row in (trip.assigned_requests or [])),
            ]
            if name
        )
    )


def _request_stop_map(trip):
    mapping = {
        row.transport_request: (row.get("pickup_stop"), row.get("dropoff_stop"))
        for row in (trip.assigned_requests or [])
        if row.transport_request
    }
    if trip.transport_request and trip.transport_request not in mapping:
        keys = [
            row.get("stop_key") for row in (trip.stops or []) if row.get("stop_key")
        ]
        mapping[trip.transport_request] = (
            keys[0] if keys else None,
            keys[-1] if keys else None,
        )
    return mapping


def sync_passengers(trip):
    requests = request_names(trip)
    if not requests:
        return

    stop_map = _request_stop_map(trip)
    current = {}
    for row in trip.boarding_state or []:
        key = row.get("passenger_key") or (
            f"Employee:{row.employee}" if row.employee else None
        )
        if key:
            current[key] = {
                fieldname: row.get(fieldname) for fieldname in BOARDING_STATE_FIELDS
            }

    employees = frappe.get_all(
        "Transport Request Worker",
        filters={"parent": ["in", requests], "parenttype": "Transport Request"},
        fields=["parent", "employee", "idx"],
        order_by="parent asc, idx asc",
    )
    employee_ids = list({row.employee for row in employees if row.employee})
    employee_names = (
        {
            row.name: row.employee_name
            for row in frappe.get_all(
                "Employee",
                filters={"name": ["in", employee_ids]},
                fields=["name", "employee_name"],
            )
        }
        if employee_ids
        else {}
    )

    passengers = []
    seen = set()
    for worker in employees:
        if not worker.employee:
            continue
        key = f"Employee:{worker.employee}"
        if key in seen:
            continue
        seen.add(key)
        pickup, dropoff = stop_map.get(worker.parent, (None, None))
        row = current.get(key, {})
        row.update(
            {
                "passenger_key": key,
                "passenger_type": "Employee",
                "employee": worker.employee,
                "passenger_name": employee_names.get(worker.employee)
                or worker.employee,
                "transport_request": worker.parent,
                "pickup_stop": pickup,
                "dropoff_stop": dropoff,
                "status": row.get("status") or "Pending",
            }
        )
        passengers.append(row)

    guests = frappe.get_all(
        "Transport Request Ad Hoc Passenger",
        filters={"parent": ["in", requests], "parenttype": "Transport Request"},
        fields=["parent", "full_name", "id_number", "idx"],
        order_by="parent asc, idx asc",
    )
    for guest in guests:
        identity = guest.id_number or str(guest.idx)
        key = f"Guest:{guest.parent}:{identity}"
        if key in seen:
            continue
        seen.add(key)
        pickup, dropoff = stop_map.get(guest.parent, (None, None))
        row = current.get(key, {})
        row.update(
            {
                "passenger_key": key,
                "passenger_type": "Guest",
                "employee": None,
                "passenger_name": guest.full_name,
                "id_number": guest.id_number,
                "transport_request": guest.parent,
                "pickup_stop": pickup,
                "dropoff_stop": dropoff,
                "status": row.get("status") or "Pending",
            }
        )
        passengers.append(row)

    trip.set("boarding_state", passengers)
