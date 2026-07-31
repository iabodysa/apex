# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Accommodation Occupancy Summary — one counted row per building.

WHY ``ref_doctype`` IS ``Housing Assignment`` WHILE THE QUERIES READ Building + Room.
The mismatch is real and deliberate, not an oversight. The figure this report exists to
publish IS a Housing Assignment aggregate: ``Building.current_occupants`` is written by
``frappe.db.count("Housing Assignment", {building, docstatus 1, check_out_date not
set})`` (habitat/doctype/building/building.py:226-229), and ``occupancy_percent``,
``available_capacity`` and the Full/Partial/Available room split are all derived from
that same count. Reading the pre-counted column instead of re-counting the assignments
is a query optimisation; it does not change whose records the numbers are made of. So
the DocPerm that gates the report is the DocPerm over the records it reports on, which
is what ``ref_doctype`` is for.

The gate is not the row boundary, and is not relied on as one. Every Building row is put
through ``permissions.report_building_scope`` below, and the Room query is confined to
the buildings that scope already returned, so a building-scoped Resident Supervisor sees
only their own estate on both reads. Nothing here depends on the Housing Assignment
DocPerm to keep another estate's rows out.

The output carries no resident identity — one row per building, counts only — so the
Housing Assignment rows behind the count are never themselves exposed.
"""

import frappe

from apex.habitat import permissions


def execute(filters=None):
    columns = [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 200},
        {"label": frappe._("Active Residents"), "fieldname": "active_residents", "fieldtype": "Int", "width": 130},
        {"label": frappe._("Total Capacity"), "fieldname": "total_capacity", "fieldtype": "Int", "width": 130},
        {"label": frappe._("Available Capacity"), "fieldname": "available_capacity", "fieldtype": "Int", "width": 150},
        {"label": frappe._("Occupancy %"), "fieldname": "occupancy_percent", "fieldtype": "Percent", "width": 110},
        {"label": frappe._("Full Rooms"), "fieldname": "full_rooms", "fieldtype": "Int", "width": 110},
        {"label": frappe._("Partially Occupied Rooms"), "fieldname": "partial_rooms", "fieldtype": "Int", "width": 190},
        {"label": frappe._("Available Rooms"), "fieldname": "available_rooms", "fieldtype": "Int", "width": 140},
    ]

    building_filters = {}
    if filters and filters.get("building"):
        building_filters["name"] = filters["building"]

    # [#kdg2pi]
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = building_filters.get("name")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            building_filters["name"] = ["in", allowed]

    buildings = frappe.get_all(
        "Building",
        filters=building_filters,
        fields=["name", "current_occupants", "total_capacity"],
        order_by="name asc",
    )

    if not buildings:
        return columns, []

    rooms = frappe.get_all(
        "Room",
        filters={"building": ["in", [row.name for row in buildings]]} if buildings else {},
        fields=["building", "status", "count(name) as room_count"],
        group_by="building, status",
    )

    room_map = {}
    for row in rooms:
        room_map.setdefault(row.building, {"Full": 0, "Partially Occupied": 0, "Available": 0, "Other": 0})
        if row.status in ("Full", "Partially Occupied", "Available"):
            room_map[row.building][row.status] += row.room_count
        else:
            room_map[row.building]["Other"] += row.room_count

    data = []
    for building in buildings:
        room_counts = room_map.get(
            building.name,
            {"Full": 0, "Partially Occupied": 0, "Available": 0},
        )
        active_residents = building.current_occupants or 0
        total_capacity = building.total_capacity or 0
        occupancy_percent = round(active_residents / total_capacity * 100, 2) if total_capacity else 0
        data.append({
            "building": building.name,
            "active_residents": active_residents,
            "total_capacity": total_capacity,
            "available_capacity": max(total_capacity - active_residents, 0),
            "occupancy_percent": occupancy_percent,
            "full_rooms": room_counts["Full"],
            "partial_rooms": room_counts["Partially Occupied"],
            "available_rooms": room_counts["Available"],
        })

    return columns, data
