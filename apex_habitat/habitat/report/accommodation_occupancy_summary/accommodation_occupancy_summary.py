# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Accommodation Building", "width": 200},
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

    buildings = frappe.get_all(
        "Accommodation Building",
        filters=building_filters,
        fields=["name", "current_occupants", "total_capacity", "occupancy_percent"],
        order_by="name asc",
    )

    if not buildings:
        return columns, []

    rooms = frappe.get_all(
        "Accommodation Room",
        filters={"building": ["in", [row.name for row in buildings]]} if buildings else {},
        fields=["building", "status", "count(name) as room_count"],
        group_by="building, status",
    )

    room_map = {}
    for row in rooms:
        room_map.setdefault(row.building, {"Full": 0, "Partially Occupied": 0, "Available": 0})
        if row.status in room_map[row.building]:
            room_map[row.building][row.status] += row.room_count

    data = []
    for building in buildings:
        room_counts = room_map.get(
            building.name,
            {"Full": 0, "Partially Occupied": 0, "Available": 0},
        )
        active_residents = building.current_occupants or 0
        total_capacity = building.total_capacity or 0
        data.append({
            "building": building.name,
            "active_residents": active_residents,
            "total_capacity": total_capacity,
            "available_capacity": max(total_capacity - active_residents, 0),
            "occupancy_percent": building.occupancy_percent or 0,
            "full_rooms": room_counts["Full"],
            "partial_rooms": room_counts["Partially Occupied"],
            "available_rooms": room_counts["Available"],
        })

    return columns, data
