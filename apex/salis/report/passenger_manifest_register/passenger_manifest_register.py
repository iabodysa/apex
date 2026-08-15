# Copyright (c) 2026, afmcoltd

"""Passenger Manifest Register — who was on which vehicle, and who never boarded.

The rows are PASSENGER rows, not documents: a manifest of forty passengers where one
never boarded is one document and forty lines, and rolling it up to the document would
hide the passenger that matters. Only submitted manifests are listed — a draft has not
dispatched, and a cancelled manifest is out with docstatus 2.

Scoped by the route plan's project through the same resolver the permission hook uses,
so a scope correction reaches this report and the desk list together.
"""

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.salis import permissions


def execute(filters=None):
    """Returns the columns, per-passenger rows and summary cards for the Passenger Manifest Register."""
    filters = filters or {}
    columns = _columns()

    query_filters = {"docstatus": 1}
    for field in ("route_plan", "vehicle", "driver"):
        if filters.get(field):
            query_filters[field] = filters[field]
    date_condition = date_range_condition(filters, "dispatch_date")
    if date_condition is not None:
        query_filters["dispatch_date"] = date_condition

    restrict, allowed = permissions.report_project_scope(frappe.session.user, doctype="Passenger Manifest")
    if restrict:
        in_scope = frappe.get_all("Route Plan", filters={"project": ["in", allowed]}, pluck="name") if allowed else []
        chosen = query_filters.get("route_plan")
        if not in_scope or (chosen and chosen not in in_scope):
            return columns, [], None, None, _summary([])
        if not chosen:
            query_filters["route_plan"] = ["in", in_scope]

    manifests = frappe.get_all(
        "Passenger Manifest",
        filters=query_filters,
        fields=["name", "dispatch_date", "route_plan", "dispatch_trip", "vehicle", "driver"],
        order_by="dispatch_date desc",
    )
    if not manifests:
        return columns, [], None, None, _summary([])

    passengers = frappe.get_all(
        "Passenger Manifest Item",
        filters={"parent": ["in", [m.name for m in manifests]], "parenttype": "Passenger Manifest"},
        fields=["parent", "employee", "passenger_name", "pickup", "dropoff", "boarded"],
        order_by="parent asc, idx asc",
    )
    by_name = {m.name: m for m in manifests}

    data = []
    for passenger in passengers:
        header = by_name.get(passenger.parent)
        if not header:
            continue
        data.append(
            {
                "name": passenger.parent,
                "dispatch_date": header.dispatch_date,
                "route_plan": header.route_plan,
                "dispatch_trip": header.dispatch_trip,
                "vehicle": header.vehicle,
                "driver": header.driver,
                "employee": passenger.employee,
                "passenger_name": passenger.passenger_name,
                "pickup": passenger.pickup,
                "dropoff": passenger.dropoff,
                "boarded": passenger.boarded,
            }
        )

    if filters.get("not_boarded_only"):
        data = [r for r in data if not r["boarded"]]

    return columns, data, None, None, _summary(data)


def _summary(data):
    """Built for any result including none, so an empty register reads 0 rather than a
    blank strip that looks like a page which failed to load."""
    manifests = {r.get("name") for r in data if r.get("name")}
    boarded = [r for r in data if r.get("boarded")]
    return [
        count_card(_("Passengers"), data),
        count_card(_("Manifests"), [{"n": n} for n in manifests]),
        count_card(_("Boarded"), boarded, indicator="Green" if boarded else None),
        percent_card(_("Boarding Rate"), len(boarded), len(data)),
    ]


def _columns():
    """Returns the column definitions for the Passenger Manifest Register report."""
    return [
        {"label": _("Manifest"), "fieldname": "name", "fieldtype": "Link", "options": "Passenger Manifest", "width": 150},
        {"label": _("Dispatch Date"), "fieldname": "dispatch_date", "fieldtype": "Date", "width": 115},
        {"label": _("Route Plan"), "fieldname": "route_plan", "fieldtype": "Link", "options": "Route Plan", "width": 150},
        {"label": _("Trip"), "fieldname": "dispatch_trip", "fieldtype": "Link", "options": "Dispatch Trip", "width": 150},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 140},
        {"label": _("Driver"), "fieldname": "driver", "fieldtype": "Link", "options": "Salis Driver", "width": 150},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": _("Passenger Name"), "fieldname": "passenger_name", "fieldtype": "Data", "width": 170},
        {"label": _("Pickup"), "fieldname": "pickup", "fieldtype": "Data", "width": 130},
        {"label": _("Dropoff"), "fieldname": "dropoff", "fieldtype": "Data", "width": 130},
        {"label": _("Boarded"), "fieldname": "boarded", "fieldtype": "Check", "width": 90},
    ]
