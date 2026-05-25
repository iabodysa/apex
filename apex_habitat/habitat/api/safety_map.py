"""Safety Map API (v0.9.0).

A thin presentation + orchestration layer over Maintenance Request, Custody
Damage Assessment, and the Safety Inspection Report controller. This module adds
NO maintenance-request, posting, or ledger logic of its own.

Two intentionally distinct signal layers:

- Room-level (maintenance/damage): each room tile gets a server-computed
  ``signal`` (red / amber / green) driven by open Maintenance Requests and a
  building-level recent-damage flag. The client must NOT recompute the signal.
- Building/floor-level (safety): safety findings (fire exits, extinguishers,
  corridors, common areas) are inherently a building/floor concern, NOT a
  per-bedroom concern. They are logged via :func:`log_building_inspection`,
  which builds and submits a building-scoped Safety Inspection Report. We do NOT
  force a ``room`` field onto the report or onto Inspection Finding Item; floor /
  zone context is carried in a seeded finding row and in the notes.

:func:`get_safety_map` is read-only and built from a BOUNDED set of bulk queries
(no N+1): one rooms query, one open-Maintenance-Request query grouped by room in
Python, and one recent Custody Damage Assessment count (building-level).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, now, today

# Maintenance Request statuses considered "open" for the room signal. Must stay
# in sync with the Maintenance Request.status Select options.
_OPEN_MAINTENANCE_STATUSES = ["Open", "Assigned", "In Progress", "Reopened"]

# Priorities that escalate a room to a red pulse.
_RED_PRIORITIES = {"High", "Critical"}

# Recency window (days) for the building-level damage signal.
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

    Each floor also gets a per-floor common-zone tile so the operator can log a
    building/floor-scoped Safety Inspection Report against shared areas.

    Args:
        building: Accommodation Building docname (source of truth).

    Returns:
        dict shaped as ``{building, building_title, generated_on,
        recent_damage_count, has_recent_damage, summary, floors}`` where each
        floor carries ``rooms`` (with flags ``has_open_maintenance``,
        ``maintenance_count``, ``has_recent_damage``, ``signal``) and a
        ``common_zone`` tile.
    """
    frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)

    building_title = (
        frappe.db.get_value("Accommodation Building", building, "building_name") or building
    )

    # Q1 — rooms in the building.
    rooms = frappe.get_all(
        "Accommodation Room",
        filters={"building": building},
        fields=["name", "room_number", "floor", "room_type", "status", "readiness_status"],
    )

    # Q2 — open maintenance requests in the building (bulk; grouped in Python).
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

    # Q3 — recent damage assessments in the building (building-level signal).
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

    # Compute per-room signal and group rooms under floors.
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


@frappe.whitelist(methods=["POST"])
def log_building_inspection(building, floor=None, zone_label=None,
                            overall_result=None, notes=None):
    """Build and submit a Safety Inspection Report at BUILDING/FLOOR scope.

    By design, safety is evaluated at the building/floor level (fire exits,
    extinguishers, corridors, common areas), NOT per bedroom — so this endpoint
    does NOT take a ``room`` and the Safety Inspection Report stays
    building-scoped (no room field is forced onto the DocType). An optional
    ``floor`` and/or ``zone_label`` narrows the finding to a floor or common
    zone; they are carried into the seeded finding row's description and into the
    report notes (the roadmap decision — carry scope as context, not a room
    link).

    The inspector is ``frappe.session.user``. A single Inspection Finding Item is
    seeded into ``safety_findings`` so the report is meaningful on submit; its
    severity maps from ``overall_result`` (Fail -> High, Needs Attention ->
    Medium, otherwise Low). The Safety Inspection Report controller then runs
    natively (including any on-submit maintenance-request generation) — this
    method adds none of that logic itself.

    Permission: caller must have ``create`` AND ``submit`` on Safety Inspection
    Report (checked explicitly below; defense in depth over the role grant).

    Args:
        building: Accommodation Building docname (source of truth).
        floor: optional floor label/number, descriptive scope only.
        zone_label: optional common-zone label, descriptive scope only.
        overall_result: optional Select-like result ("Pass" / "Needs Attention"
            / "Fail"); maps to the seeded finding severity.
        notes: optional free-text observation appended to the finding.

    Returns:
        dict: ``{"report": <Safety Inspection Report docname>, "building": ...,
        "floor": ..., "zone_label": ...}``.
    """
    frappe.has_permission("Safety Inspection Report", "create", throw=True)
    frappe.has_permission("Safety Inspection Report", "submit", throw=True)

    if not building:
        frappe.throw(_("A building is required to log an inspection."))

    # Build the scope-prefixed description carried in the seeded finding row.
    scope_bits = []
    if floor:
        scope_bits.append(_("Floor {0}").format(floor))
    if zone_label:
        scope_bits.append(zone_label)
    scope_prefix = " / ".join(scope_bits)

    description = notes or _("Building safety inspection.")
    if scope_prefix:
        description = f"{scope_prefix}: {description}"

    # Map the operator's overall result to a finding severity / clear flag.
    severity = "Low"
    safety_clear = 0
    if overall_result == "Fail":
        severity = "High"
    elif overall_result == "Needs Attention":
        severity = "Medium"
    elif overall_result == "Pass":
        severity = "Low"
        safety_clear = 1

    doc = frappe.get_doc(
        {
            "doctype": "Safety Inspection Report",
            "building": building,
            "inspection_date": today(),
            "inspector": frappe.session.user,
            "safety_section_clear": safety_clear,
            "safety_findings": [
                {
                    "finding_category": "Safety",
                    "description": description,
                    "severity": severity,
                    "status": "Open",
                }
            ],
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {
        "report": doc.name,
        "building": building,
        "floor": floor,
        "zone_label": zone_label,
    }
