# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

import frappe

from apex_habitat.habitat import permissions


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

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions; re-apply it on the building identity.
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
