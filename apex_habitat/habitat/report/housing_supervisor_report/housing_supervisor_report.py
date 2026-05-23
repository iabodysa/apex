# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.utils import add_days, getdate, today


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("period_from") or add_days(today(), -7))
    date_to = getdate(filters.get("period_to") or today())
    building_filter = filters.get("building")

    columns = _columns()
    buildings = _get_buildings(building_filter)
    if not buildings:
        return columns, []

    building_names = [b.name for b in buildings]

    occupancy = _occupancy(building_names)
    cleaning = _cleaning(building_names, date_from, date_to)
    safety = _safety_inspections(building_names, date_from, date_to)
    maintenance = _maintenance(building_names)
    resident = _resident_requests(building_names)

    data = []
    for b in buildings:
        n = b.name
        total = occupancy[n]["total"]
        occ = occupancy[n]["occupied"]
        occ_pct = round(occ / total * 100, 1) if total else 0.0

        cl = cleaning[n]
        compliance = round(cl["compliant"] / cl["total"] * 100, 1) if cl["total"] else 0.0

        data.append({
            "building": n,
            "total_beds": total,
            "occupied_beds": occ,
            "occupancy_pct": occ_pct,
            "cleaning_logs": cl["total"],
            "cleaning_compliance_pct": compliance,
            "missed_cleaning_logs": cl["missed"],
            "safety_inspections": safety[n],
            "open_maintenance": maintenance[n]["open"],
            "closed_maintenance": maintenance[n]["closed"],
            "open_resident_requests": resident[n],
        })

    return columns, data


def _columns():
    return [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link",
         "options": "Accommodation Building", "width": 180},
        {"label": frappe._("Total Beds"), "fieldname": "total_beds", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Occupied Beds"), "fieldname": "occupied_beds", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Occupancy %"), "fieldname": "occupancy_pct", "fieldtype": "Float",
         "precision": 1, "width": 100},
        {"label": frappe._("Cleaning Logs"), "fieldname": "cleaning_logs", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Cleaning Compliance %"), "fieldname": "cleaning_compliance_pct",
         "fieldtype": "Float", "precision": 1, "width": 150},
        {"label": frappe._("Missed Cleaning Logs"), "fieldname": "missed_cleaning_logs",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Safety Inspections"), "fieldname": "safety_inspections",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Open Maintenance"), "fieldname": "open_maintenance",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Closed Maintenance"), "fieldname": "closed_maintenance",
         "fieldtype": "Int", "width": 140},
        {"label": frappe._("Open Resident Requests"), "fieldname": "open_resident_requests",
         "fieldtype": "Int", "width": 160},
    ]


def _get_buildings(building_filter):
    f = {"status": "Active"}
    if building_filter:
        f["name"] = building_filter
    return frappe.get_all("Accommodation Building", filters=f, fields=["name"], order_by="name")


def _occupancy(building_names):
    result = defaultdict(lambda: {"total": 0, "occupied": 0})

    beds = frappe.get_all("Accommodation Bed", filters={"building": ["in", building_names]},
                           fields=["building", "status"])
    for bed in beds:
        result[bed.building]["total"] += 1
        if bed.status == "Occupied":
            result[bed.building]["occupied"] += 1

    return result


def _cleaning(building_names, date_from, date_to):
    result = defaultdict(lambda: {"total": 0, "compliant": 0, "missed": 0})

    logs = frappe.get_all(
        "Cleaning Log",
        filters={"building": ["in", building_names],
                 "cleaning_date": ["between", [str(date_from), str(date_to)]]},
        fields=["building", "missed_cleaning"],
    )
    for log in logs:
        b = log.building
        result[b]["total"] += 1
        if log.missed_cleaning:
            result[b]["missed"] += 1
        else:
            result[b]["compliant"] += 1

    return result


def _safety_inspections(building_names, date_from, date_to):
    result = defaultdict(int)
    rows = frappe.get_all(
        "Safety Inspection Report",
        filters={"building": ["in", building_names], "docstatus": 1,
                 "inspection_date": ["between", [str(date_from), str(date_to)]]},
        fields=["building"],
    )
    for r in rows:
        result[r.building] += 1
    return result


def _maintenance(building_names):
    result = defaultdict(lambda: {"open": 0, "closed": 0})
    rows = frappe.get_all(
        "Maintenance Request",
        filters={"building": ["in", building_names]},
        fields=["building", "status"],
    )
    for r in rows:
        if r.status in ("Open", "In Progress"):
            result[r.building]["open"] += 1
        elif r.status == "Resolved":
            result[r.building]["closed"] += 1
    return result


def _resident_requests(building_names):
    result = defaultdict(int)
    tokens = frappe.get_all(
        "Accommodation QR Location",
        filters={"building": ["in", building_names]},
        fields=["name", "building"],
    )
    token_to_building = {t.name: t.building for t in tokens}
    if not token_to_building:
        return result

    requests = frappe.get_all(
        "Accommodation Resident Request",
        filters={"location_token": ["in", list(token_to_building.keys())],
                 "status": ["in", ["Open", "Triaged"]]},
        fields=["location_token"],
    )
    for r in requests:
        building = token_to_building.get(r.location_token)
        if building:
            result[building] += 1
    return result
