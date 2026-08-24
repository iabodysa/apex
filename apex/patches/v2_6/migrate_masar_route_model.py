# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from collections import defaultdict

import frappe


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


def execute():
    _backfill_stop_keys("Route Template")
    _backfill_stop_keys("Route Plan")
    _backfill_route_assignments()
    _backfill_dispatch_trips()
    _backfill_request_stop_mappings()


def _single_distinct(values):
    unique = {value for value in values if value}
    return next(iter(unique)) if len(unique) == 1 else None


def _missing_stop_keys(rows):
    used = {row.stop_key for row in rows if row.stop_key}
    values = {}
    for position, row in enumerate(rows, start=1):
        if row.stop_key:
            continue
        number = row.idx or position
        key = f"stop-{number}"
        while key in used:
            number += 1
            key = f"stop-{number}"
        used.add(key)
        values[row.name] = key
    return values


def _backfill_stop_keys(parenttype):
    rows = frappe.get_all(
        "Route Stop",
        filters={"parenttype": parenttype},
        fields=["name", "parent", "stop_key", "idx"],
        order_by="parent asc, idx asc",
    )
    by_parent = defaultdict(list)
    for row in rows:
        by_parent[row.parent].append(row)
    for parent_rows in by_parent.values():
        for name, key in _missing_stop_keys(parent_rows).items():
            frappe.db.set_value(
                "Route Stop", name, "stop_key", key, update_modified=False
            )


def _backfill_route_assignments():
    legacy_fields = ["name"]
    for fieldname in ("project", "start_date"):
        if frappe.db.has_column("Work Shift", fieldname):
            legacy_fields.append(fieldname)
    shifts = {
        row.name: row
        for row in frappe.get_all("Work Shift", fields=legacy_fields + ["shift_name"])
    }
    plans_by_assignment = defaultdict(list)
    for row in frappe.get_all(
        "Route Plan",
        filters={"route_assignment": ["is", "set"]},
        fields=["route_assignment", "driver", "vehicle", "route_supervisor"],
    ):
        plans_by_assignment[row.route_assignment].append(row)

    for assignment in frappe.get_all(
        "Route Assignment",
        fields=[
            "name",
            "assignment_name",
            "route_template",
            "work_shift",
            "shift_name",
            "project",
            "driver",
            "vehicle",
            "route_supervisor",
            "starts_on",
        ],
    ):
        shift = shifts.get(assignment.work_shift) or frappe._dict()
        plans = plans_by_assignment.get(assignment.name, [])
        values = {}
        if not assignment.project and shift.get("project"):
            values["project"] = shift.project
        if not assignment.starts_on and shift.get("start_date"):
            values["starts_on"] = shift.start_date
        if not assignment.shift_name and shift.get("shift_name"):
            values["shift_name"] = shift.shift_name
        for fieldname in ("driver", "vehicle", "route_supervisor"):
            if not assignment.get(fieldname):
                value = _single_distinct(row.get(fieldname) for row in plans)
                if value:
                    values[fieldname] = value

        merged = frappe._dict({**assignment, **values})
        if not assignment.assignment_name:
            title = _assignment_title(merged)
            if title:
                values["assignment_name"] = title
        if values:
            frappe.db.set_value(
                "Route Assignment", assignment.name, values, update_modified=False
            )


def _assignment_title(assignment):
    route = (
        frappe.db.get_value(
            "Route Template", assignment.route_template, "template_name"
        )
        if assignment.route_template
        else None
    )
    project = (
        frappe.db.get_value("Project", assignment.project, "project_name")
        if assignment.project
        else None
    )
    return " · ".join(
        value
        for value in (route, assignment.shift_name or assignment.work_shift, project)
        if value
    )[:140]


def _trip_context_values(trip, plan, assignment=None):
    assignment = assignment or frappe._dict()
    candidates = {
        "transport_request": plan.transport_request,
        "route_assignment": plan.route_assignment,
        "route_template": assignment.get("route_template"),
        "project": plan.project or assignment.get("project"),
        "vehicle": plan.vehicle,
        "driver": plan.driver,
        "shift_name": assignment.get("shift_name") or plan.shift,
    }
    values = {
        fieldname: value
        for fieldname, value in candidates.items()
        if value and not trip.get(fieldname)
    }
    if not trip.trip_title and plan.route_name:
        values["trip_title"] = f"{plan.route_name} · {trip.trip_date}"[:140]
    return values


def _backfill_dispatch_trips():
    assignments = {
        row.name: row
        for row in frappe.get_all(
            "Route Assignment",
            fields=["name", "route_template", "project", "shift_name"],
        )
    }
    plans = {
        row.name: row
        for row in frappe.get_all(
            "Route Plan",
            fields=[
                "name",
                "route_name",
                "transport_request",
                "route_assignment",
                "project",
                "vehicle",
                "driver",
                "shift",
            ],
        )
    }
    for trip in frappe.get_all(
        "Dispatch Trip",
        filters={"route_plan": ["is", "set"]},
        fields=[
            "name",
            "route_plan",
            "trip_title",
            "trip_date",
            "transport_request",
            "route_assignment",
            "route_template",
            "project",
            "vehicle",
            "driver",
            "shift_name",
        ],
    ):
        plan = plans.get(trip.route_plan)
        if not plan:
            continue
        assignment = assignments.get(plan.route_assignment)
        values = _trip_context_values(trip, plan, assignment)
        if values:
            frappe.db.set_value(
                "Dispatch Trip", trip.name, values, update_modified=False
            )
        _copy_plan_stops_to_trip(plan.name, trip.name)


def _copy_plan_stops_to_trip(route_plan, dispatch_trip):
    if frappe.db.exists(
        "Route Stop", {"parent": dispatch_trip, "parenttype": "Dispatch Trip"}
    ):
        return
    source = frappe.get_all(
        "Route Stop",
        filters={"parent": route_plan, "parenttype": "Route Plan"},
        fields=["idx", *ROUTE_STOP_FIELDS],
        order_by="idx asc",
    )
    for row in source:
        values = {fieldname: row.get(fieldname) for fieldname in ROUTE_STOP_FIELDS}
        frappe.get_doc(
            {
                "doctype": "Route Stop",
                "parent": dispatch_trip,
                "parenttype": "Dispatch Trip",
                "parentfield": "stops",
                "idx": row.idx,
                **values,
            }
        ).db_insert()


def _backfill_request_stop_mappings():
    trips = frappe.get_all(
        "Dispatch Trip",
        filters={"route_plan": ["is", "set"]},
        pluck="name",
    )
    for trip in trips:
        stops = frappe.get_all(
            "Route Stop",
            filters={"parent": trip, "parenttype": "Dispatch Trip"},
            pluck="stop_key",
            order_by="idx asc",
        )
        if not stops or len(stops) > 2:
            continue
        pickup, dropoff = stops[0], stops[-1]
        for row in frappe.get_all(
            "Dispatch Trip Assigned Request",
            filters={"parent": trip, "parenttype": "Dispatch Trip"},
            fields=["name", "pickup_stop", "dropoff_stop"],
        ):
            values = {}
            if not row.pickup_stop:
                values["pickup_stop"] = pickup
            if not row.dropoff_stop:
                values["dropoff_stop"] = dropoff
            if values:
                frappe.db.set_value(
                    "Dispatch Trip Assigned Request",
                    row.name,
                    values,
                    update_modified=False,
                )
