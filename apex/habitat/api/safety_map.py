# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, now, today

_OPEN_MAINTENANCE_STATUSES = ["Open", "In Progress", "Resolved"]

_RED_PRIORITIES = {"High", "Critical"}

_DAMAGE_RECENCY_DAYS = 14


@frappe.whitelist()
def get_safety_map(building=None):
    if not building:
        frappe.throw(_("A building is required to draw the safety map."))
    frappe.has_permission("Building", "read", doc=building, throw=True)

    building_title = (
        frappe.db.get_value("Building", building, "building_name") or building
    )

    rooms = frappe.get_list(
        "Room",
        filters={"building": building},
        fields=["name", "room_number", "floor", "room_type", "status", "readiness_status"],
        limit_page_length=0,
    )

    maint_rows = frappe.get_list(
        "Maintenance Request",
        filters={
            "building": building,
            "docstatus": 1,
            "status": ["in", _OPEN_MAINTENANCE_STATUSES],
        },
        fields=["name", "room", "priority", "status"],
        limit_page_length=0,
    )
    maint_by_room: dict[str, dict] = {}
    for m in maint_rows:
        if not m.room:
            continue
        agg = maint_by_room.setdefault(m.room, {"count": 0, "has_red": False})
        agg["count"] += 1
        if m.priority in _RED_PRIORITIES:
            agg["has_red"] = True

    cutoff = add_days(today(), -_DAMAGE_RECENCY_DAYS)
    recent_damage_count = frappe.db.count(
        "Custody Damage Assessment",
        {
            "building": building,
            "docstatus": 1,
            "assessment_date": [">=", cutoff],
        },
    )
    has_recent_damage = bool(recent_damage_count)

    summary = {"total_rooms": 0, "red": 0, "amber": 0, "green": 0}
    floors_acc: dict = {}

    for room in rooms:
        agg = maint_by_room.get(room.name, {"count": 0, "has_red": False})
        maintenance_count = agg["count"]
        has_open_maintenance = maintenance_count > 0

        if agg["has_red"]:
            signal = "red"
        elif has_open_maintenance or has_recent_damage:
            signal = "amber"
        else:
            signal = "green"

        summary["total_rooms"] += 1
        summary[signal] += 1

        room_payload = {
            "room": room.name,
            "room_number": room.room_number or room.name,
            "room_type": room.room_type,
            "floor": room.floor,
            "readiness_status": room.readiness_status,
            "has_open_maintenance": has_open_maintenance,
            "maintenance_count": maintenance_count,
            "has_recent_damage": has_recent_damage,
            "signal": signal,
        }

        key = room.floor if room.floor else None
        floors_acc.setdefault(key, []).append(room_payload)

    floors = []
    numbered = sorted((k for k in floors_acc if k is not None))
    for floor in numbered:
        floors.append(_build_floor(floor, floors_acc[floor], _("Floor {0}").format(floor)))
    if None in floors_acc:
        floors.append(_build_floor(0, floors_acc[None], _("Unassigned Floor")))

    return {
        "building": building,
        "building_title": building_title,
        "generated_on": now(),
        "recent_damage_count": recent_damage_count,
        "has_recent_damage": has_recent_damage,
        "summary": summary,
        "floors": floors,
    }


def _build_floor(floor, rooms_list, floor_label):
    rooms_sorted = sorted(rooms_list, key=lambda r: str(r.get("room_number") or ""))
    return {
        "floor": floor,
        "floor_label": floor_label,
        "rooms": rooms_sorted,
        "common_zone": {
            "zone_label": _("Common Area"),
            "signal": "zone",
        },
    }
