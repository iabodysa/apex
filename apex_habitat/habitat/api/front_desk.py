"""Front Desk visual bed board API (v0.8.6).

A thin presentation + orchestration layer over the existing Accommodation
Assignment / Accommodation Checkout controllers. This module adds NO posting,
locking, or ledger logic of its own:

- ``get_building_grid`` is read-only and built from a bounded set of bulk
  queries (no N+1) — one room query, one bed/room join, one active-assignment
  query, and one custody-presence query.
- ``quick_check_in`` and ``quick_check_out`` construct documents and submit
  them so the existing controllers run natively (the ``SELECT ... FOR UPDATE``
  bed lock, occupancy recompute, housing-allowance gate, and custody-clearance
  gate all stay in place).

Active-occupancy semantics throughout: ``docstatus == 1`` AND
``check_out_date`` is not set.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now, today


def _bed_color(bed_status: str, condition: str, readiness_status: str) -> str:
    """Resolve the Front Desk bed color. First matching rule wins (top-down).

    1. Out of Service / Scrapped  -> grey  (disabled)
    2. Occupied                   -> red   (active occupant)
    3. Available + room Ready/Unknown            -> green (clickable)
    4. Available + room not ready (cleaning/repair/oos) -> amber (warning)
    5. fallback                   -> grey
    """
    if bed_status == "Out of Service" or condition == "Scrapped":
        return "grey"
    if bed_status == "Occupied":
        return "red"
    if bed_status == "Available":
        if readiness_status in ("Ready", "Unknown"):
            return "green"
        if readiness_status in ("Needs Cleaning", "Needs Repair", "Out of Service"):
            return "amber"
    return "grey"


@frappe.whitelist()
def get_building_grid(building: str) -> dict:
    """Return the floor -> room -> bed grid for one building for the Front Desk board.

    Reads only. Permission-gated on the building. Built from a BOUNDED set of
    bulk queries (no per-bed or per-room round trips). Each bed gets a
    server-computed ``bed_color`` (see ``_bed_color``); the client must not
    recompute color.

    Args:
        building: Accommodation Building docname (source of truth).

    Returns:
        dict shaped as ``{building, building_title, generated_on, summary, floors}``.
    """
    frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)

    building_title = frappe.db.get_value("Accommodation Building", building, "building_name") or building

    # Q1 — rooms in the building.
    rooms = frappe.get_all(
        "Accommodation Room",
        filters={"building": building},
        fields=[
            "name",
            "room_number",
            "floor",
            "room_type",
            "readiness_status",
            "status",
            "bed_capacity",
            "current_occupancy",
        ],
    )
    rooms_by_name = {r.name: r for r in rooms}

    # Q2 — beds in the building joined to their room (one query; the join
    # replaces per-bed room lookups).
    Bed = frappe.qb.DocType("Accommodation Bed")
    Room = frappe.qb.DocType("Accommodation Room")
    bed_rows = (
        frappe.qb.from_(Bed)
        .left_join(Room)
        .on(Bed.room == Room.name)
        .select(
            Bed.name.as_("bed"),
            Bed.bed_code,
            Bed.room,
            Bed.status.as_("bed_status"),
            Bed.condition,
            Room.floor.as_("room_floor"),
            Room.room_type.as_("room_type"),
            Room.readiness_status.as_("readiness_status"),
        )
        .where(Bed.building == building)
        .run(as_dict=True)
    )

    # Q3 — active assignments in the building.
    assignments = frappe.get_all(
        "Accommodation Assignment",
        filters={
            "building": building,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        },
        fields=["name", "bed", "employee", "employee_name", "project", "check_in_date"],
    )
    assignments_by_bed = {a.bed: a for a in assignments}

    # Q4 — custody presence per active assignment (one bulk query, grouped by
    # parent — NOT one query per assignment).
    custody_parents: set[str] = set()
    assignment_names = [a.name for a in assignments]
    if assignment_names:
        custody_rows = frappe.get_all(
            "Accommodation Custody Item",
            filters={
                "parenttype": "Accommodation Assignment",
                "parent": ["in", assignment_names],
            },
            fields=["parent"],
            distinct=True,
        )
        custody_parents = {c.parent for c in custody_rows}

    # Merge in Python — group beds under rooms, rooms under floors.
    summary = {"total_beds": 0, "available": 0, "occupied": 0, "blocked": 0, "out_of_service": 0}
    rooms_acc: dict[str, dict] = {}

    for bed in bed_rows:
        color = _bed_color(bed.bed_status, bed.condition, bed.readiness_status)
        summary["total_beds"] += 1
        if color == "green":
            summary["available"] += 1
        elif color == "red":
            summary["occupied"] += 1
        elif color == "amber":
            summary["blocked"] += 1
        else:
            summary["out_of_service"] += 1

        occupant = None
        if color == "red":
            asg = assignments_by_bed.get(bed.bed)
            if asg:
                occupant = {
                    "assignment": asg.name,
                    "employee": asg.employee,
                    "employee_name": asg.employee_name,
                    "project": asg.project,
                    "check_in_date": str(asg.check_in_date) if asg.check_in_date else None,
                    "has_custody": asg.name in custody_parents,
                }

        bed_payload = {
            "bed": bed.bed,
            "bed_code": bed.bed_code,
            "bed_status": bed.bed_status,
            "condition": bed.condition,
            "bed_color": color,
            "occupant": occupant,
        }

        room_name = bed.room
        if room_name not in rooms_acc:
            room_meta = rooms_by_name.get(room_name)
            rooms_acc[room_name] = {
                "room": room_name,
                "room_number": room_meta.room_number if room_meta else room_name,
                "room_type": bed.room_type,
                "readiness_status": bed.readiness_status,
                "room_status": room_meta.status if room_meta else None,
                "bed_capacity": room_meta.bed_capacity if room_meta else None,
                "current_occupancy": room_meta.current_occupancy if room_meta else None,
                "_floor": bed.room_floor,
                "beds": [],
            }
        rooms_acc[room_name]["beds"].append(bed_payload)

    # Group rooms by floor. Rooms with null/0 floor go to an "Unassigned" bucket.
    floors_acc: dict = {}
    for room in rooms_acc.values():
        floor = room.pop("_floor")
        key = floor if floor else None
        if key not in floors_acc:
            floors_acc[key] = []
        floors_acc[key].append(room)

    floors = []
    numbered = sorted((k for k in floors_acc if k is not None))
    for floor in numbered:
        rooms_list = sorted(floors_acc[floor], key=lambda r: str(r.get("room_number") or ""))
        floors.append(
            {
                "floor": floor,
                "floor_label": _("Floor {0}").format(floor),
                "rooms": rooms_list,
            }
        )
    if None in floors_acc:
        rooms_list = sorted(floors_acc[None], key=lambda r: str(r.get("room_number") or ""))
        floors.append(
            {
                "floor": 0,
                "floor_label": _("Unassigned Floor"),
                "rooms": rooms_list,
            }
        )

    return {
        "building": building,
        "building_title": building_title,
        "generated_on": now(),
        "summary": summary,
        "floors": floors,
    }


@frappe.whitelist(methods=["POST"])
def quick_check_in(bed, employee, project, check_in_date,
                   cost_center=None, assignment_type="New Assignment"):
    """Create and submit an Accommodation Assignment from the Front Desk board.

    Room and building are derived SERVER-SIDE from the bed (never trusted from
    the client). A full Accommodation Assignment is built and submitted so ALL
    native controller behavior runs: field validation, the ``SELECT ... FOR
    UPDATE`` bed lock, the double-booking re-check, ``bed.status -> Occupied``,
    room/building occupancy recompute, and housing-allowance suspension.

    This method adds NO posting, locking, or ledger logic of its own.

    Permission: caller must have ``create`` AND ``submit`` on Accommodation
    Assignment (checked explicitly below; defense in depth on top of the role
    grant).

    Args:
        bed: Accommodation Bed docname (source of truth for room + building).
        employee: Employee docname.
        project: Project docname.
        check_in_date: ISO date string.
        cost_center: optional Cost Center docname.
        assignment_type: Select value (defaults to "New Assignment").

    Returns:
        dict: ``{"assignment": <docname>, "bed": <bed>}``.
    """
    frappe.has_permission("Accommodation Assignment", "create", throw=True)
    frappe.has_permission("Accommodation Assignment", "submit", throw=True)

    room, building = frappe.db.get_value("Accommodation Bed", bed, ["room", "building"])
    if not room or not building:
        frappe.throw(_("Bed {0} is not linked to a room and building.").format(bed))

    doc = frappe.get_doc(
        {
            "doctype": "Accommodation Assignment",
            "bed": bed,
            "room": room,
            "building": building,
            "employee": employee,
            "project": project,
            "check_in_date": check_in_date,
            "cost_center": cost_center,
            "assignment_type": assignment_type or "New Assignment",
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"assignment": doc.name, "bed": bed}


@frappe.whitelist(methods=["POST"])
def quick_check_out(bed, checkout_date=None, checkout_reason=None):
    """Build and submit an Accommodation Checkout for the active assignment on a bed.

    Resolves the single active assignment for the bed server-side
    (``docstatus == 1`` AND ``check_out_date`` is not set). If that assignment
    carries custody items, this method REFUSES one-click and signals the client
    to open the full Checkout form instead (returns
    ``{"requires_full_form": True, "assignment": <name>}``), because custody
    clearance and damage-assessment logic must run interactively through the
    Checkout controller.

    Otherwise it constructs an Accommodation Checkout and submits it, letting
    the existing Checkout controller run its validation, occupancy/bed release,
    and posting logic. This method adds NO release or ledger logic of its own.

    Permission: caller must have ``create`` AND ``submit`` on Accommodation
    Checkout (checked explicitly below).

    Args:
        bed: Accommodation Bed docname.
        checkout_date: ISO date string; defaults to today if omitted.
        checkout_reason: Select value for the Checkout reason.

    Returns:
        dict: ``{"checkout": <docname>, "bed": <bed>}`` on a completed one-click
        checkout, or ``{"requires_full_form": True, "assignment": <name>}`` when
        custody routing is needed.
    """
    frappe.has_permission("Accommodation Checkout", "create", throw=True)
    frappe.has_permission("Accommodation Checkout", "submit", throw=True)

    assignment = frappe.db.get_value(
        "Accommodation Assignment",
        {"bed": bed, "docstatus": 1, "check_out_date": ["is", "not set"]},
        "name",
    )
    if not assignment:
        frappe.throw(_("No active assignment found for bed {0}.").format(bed))

    # Custody gate — route to the full Checkout form so clearance + damage
    # assessment run interactively through the Checkout controller.
    has_custody = bool(
        frappe.db.exists(
            "Accommodation Custody Item",
            {"parenttype": "Accommodation Assignment", "parent": assignment},
        )
    )
    if has_custody:
        return {"requires_full_form": True, "assignment": assignment}

    doc = frappe.get_doc(
        {
            "doctype": "Accommodation Checkout",
            "assignment": assignment,
            "checkout_date": checkout_date or today(),
            "checkout_reason": checkout_reason,
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"checkout": doc.name, "bed": bed}
