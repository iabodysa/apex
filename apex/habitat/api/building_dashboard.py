# Copyright (c) 2026, AFMCO and contributors
"""On-form dashboard metrics for the Building form.

Frappe's form `get_data()` only renders the links/transactions section; the
occupancy chart and indicator counts at the top of the form are rendered
client-side (building.js) from this whitelisted reader.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_building_layout(building: str) -> dict:
    """Return a floor-grouped room layout for the building dashboard.

    One query, grouped by floor (ascending). Each room carries a server-computed
    ``room_color``:
      - green  : status "Available"
      - orange : status "Partially Occupied" OR readiness_status indicates
                 needs cleaning / repair
      - red    : status "Full"
      - grey   : status "Under Maintenance" or "Out of Service"
    """
    frappe.has_permission("Building", "read", doc=building, throw=True)

    rooms = frappe.get_all(
        "Room",
        filters={"building": building},
        fields=[
            "name",
            "room_number",
            "floor",
            "room_type",
            "status",
            "readiness_status",
            "bed_capacity",
            "current_occupancy",
        ],
    )

    _NEEDS_ATTENTION = {"Needs Cleaning", "Needs Repair"}

    def _color(room):
        s = (room.status or "").strip()
        r = (room.readiness_status or "").strip()
        if s in ("Under Maintenance", "Out of Service"):
            return "grey"
        if s == "Full":
            return "red"
        if s == "Partially Occupied" or r in _NEEDS_ATTENTION:
            return "orange"
        if s == "Available":
            return "green"
        return "grey"

    for room in rooms:
        room["room_color"] = _color(room)

    floors_map = {}
    for room in rooms:
        floor_num = room.floor if room.floor is not None else 0
        if floor_num not in floors_map:
            floors_map[floor_num] = []
        floors_map[floor_num].append(room)

    floors = []
    for floor_num in sorted(floors_map.keys()):
        floor_rooms = floors_map[floor_num]
        if floor_num == 0:
            floor_label = _("Ground Floor")
        elif floor_num < 0:
            floor_label = _("Basement {0}").format(abs(floor_num))
        else:
            floor_label = _("Floor {0}").format(floor_num)
        floors.append({
            "floor": floor_num,
            "floor_label": floor_label,
            "rooms": floor_rooms,
        })

    summary = {"available": 0, "partial": 0, "full": 0, "maintenance": 0}
    for room in rooms:
        c = room["room_color"]
        if c == "green":
            summary["available"] += 1
        elif c == "orange":
            summary["partial"] += 1
        elif c == "red":
            summary["full"] += 1
        else:
            summary["maintenance"] += 1

    return {
        "building": building,
        "total_rooms": len(rooms),
        "floors": floors,
        "summary": summary,
    }


@frappe.whitelist()
def get_building_metrics(building: str) -> dict:
    """Occupancy, maintenance and custody counters for one Building's form dashboard.

    Consumed only by ``_renderBuildingDashboard`` in building.js, which calls
    ``frm.dashboard.reset()`` before drawing these. ``reset()`` also hides the native
    Connections area, so the client must call ``render_links()`` straight after it or
    the linked-document groups (Rooms, Beds, Leases, Residents, ...) disappear from the
    form.
    """
    frappe.has_permission("Building", "read", doc=building, throw=True)

    snaps = frappe.get_all(
        "Occupancy Snapshot",
        filters={"building": building},
        fields=["snapshot_date", "occupancy_percent"],
        order_by="snapshot_date asc",
        limit_page_length=60,
    )
    return {
        "labels": [str(s.snapshot_date) for s in snaps],
        "occupancy": [flt(s.occupancy_percent) for s in snaps],
        "active_occupants": frappe.db.count(
            "Housing Assignment",
            {"building": building, "docstatus": 1, "check_out_date": ["is", "not set"]},
        ),
        "open_maintenance": frappe.db.count(
            "Maintenance Request",
            {"building": building, "status": ["not in", ["Closed", "Cancelled", "Resolved"]]},
        ),
        "open_custody": frappe.db.count(
            "Custody Issue",
            {"building": building, "docstatus": 1, "status": ["in", ["Issued", "Partially Returned"]]},
        ),
    }
