# Copyright (c) 2026, afmcoltd

"""Accommodation Occupancy Summary — one counted row per building.

The gate is not the row boundary, and is not relied on as one. Every Building row is put
through ``permissions.report_building_scope`` below, and the Room query is confined to
the buildings that scope already returned, so a building-scoped Resident Supervisor sees
only their own estate on both reads. Nothing here depends on the Housing Assignment
DocPerm to keep another estate's rows out.

The output carries no resident identity — one row per building, counts only — so the
Housing Assignment rows behind the count are never themselves exposed.
"""

import frappe
from frappe import _
from frappe.utils import flt

from apex.habitat import permissions
from apex.apex_core.utils.report_summary import count_card, percent_card, total_card


def execute(filters=None):
    """Returns one row per building with resident counts and room status split, scoped by permission."""
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

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Building")
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

    summary = [
        count_card(_("Buildings"), data),
        total_card(_("Residents"), data, "active_residents", "Int"),
        total_card(_("Total Capacity"), data, "total_capacity", "Int"),
        percent_card(
            _("Occupancy"),
            sum(flt(r.get("active_residents")) for r in data),
            sum(flt(r.get("total_capacity")) for r in data),
        ),
    ]
    return columns, data, None, None, summary
