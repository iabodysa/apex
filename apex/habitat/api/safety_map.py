# Copyright (c) 2026, AFMCO and contributors
"""Safety Map API (v0.9.0).

A READ-ONLY presentation layer over Room, Maintenance Request and Custody Damage
Assessment. This module adds NO maintenance-request, posting, or ledger logic of
its own, and since the Safety Inspection Report retirement it writes nothing at
all — the page has exactly one whitelisted endpoint, :func:`get_safety_map`.

Room tiles get a server-computed ``signal`` (red / amber / green) driven by open
Maintenance Requests and a building-level recent-damage flag. The client must NOT
recompute the signal.

Safety EVIDENCE is not written here. This module used to expose a
``log_building_inspection`` POST that built and submitted a building-scoped
Safety Inspection Report; that record is deprecated in favour of Safety Round,
and the endpoint was its last remaining producer. It also bypassed the Safety
Round maker-checker gate outright — one caller inserted AND submitted in a single
request, so the author ratified their own evidence. Common-area findings now go
through Safety Round + its Safety Task Execution rows, which the page links to
rather than writes.

:func:`get_safety_map` is read-only and built from a BOUNDED set of bulk queries
(no N+1): one rooms query, one open-Maintenance-Request query grouped by room in
Python, and one recent Custody Damage Assessment count (building-level).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, now, today

_OPEN_MAINTENANCE_STATUSES = ["Open", "Assigned", "In Progress", "Reopened"]

_RED_PRIORITIES = {"High", "Critical"}

_DAMAGE_RECENCY_DAYS = 14


@frappe.whitelist()
def get_safety_map(building):
    """Return the floor -> room safety map for one building (read-only, N+1-free).

    Built from a BOUNDED set of bulk queries:
      Q1  rooms in the building (name, room_number, floor).
      Q2  open Maintenance Requests in the building (docstatus == 1, status in
          the open set), grouped by room in Python: per-room count + whether any
          line is High/Critical priority.
      Q3  recent Custody Damage Assessments in the building (docstatus == 1,
          assessment_date >= today - N days). Custody Damage Assessment has no
          room link, so this raises a BUILDING-level amber signal surfaced on the
          summary, not per individual room.

    Each room's ``signal`` is computed server-side (first match wins):
      red   -> any open High/Critical maintenance request on the room;
      amber -> any open maintenance request on the room (lower priority), OR the
               building has a recent damage signal;
      green -> no open signals.
    The client must NOT recompute the signal.

    Each floor also gets a per-floor common-zone tile standing for the shared
    areas (corridors, fire exits, extinguishers) that no bedroom covers. It is a
    navigation affordance only: the page routes it to Safety Round, it does not
    write safety evidence.

    Args:
        building: Accommodation Building docname (source of truth).

    Returns:
        dict shaped as ``{building, building_title, generated_on,
        recent_damage_count, has_recent_damage, summary, floors}`` where each
        floor carries ``rooms`` (with flags ``has_open_maintenance``,
        ``maintenance_count``, ``has_recent_damage``, ``signal``) and a
        ``common_zone`` tile.
    """
    frappe.has_permission("Building", "read", doc=building, throw=True)

    building_title = (
        frappe.db.get_value("Building", building, "building_name") or building
    )

    rooms = frappe.get_all(
        "Room",
        filters={"building": building},
        fields=["name", "room_number", "floor", "room_type", "status", "readiness_status"],
    )

    maint_rows = frappe.get_all(
        "Maintenance Request",
        filters={
            "building": building,
            "docstatus": 1,
            "status": ["in", _OPEN_MAINTENANCE_STATUSES],
        },
        fields=["name", "room", "priority", "status"],
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
    """Assemble one floor payload: its rooms plus a single common-zone tile."""
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
