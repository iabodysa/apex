# Copyright (c) 2026, AFMCO and contributors
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
from frappe.rate_limiter import rate_limit
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
    frappe.has_permission("Building", "read", doc=building, throw=True)

    building_title = frappe.db.get_value("Building", building, "building_name") or building

    # [#nl1hpu]
    rooms = frappe.get_all(
        "Room",
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

    # [#hm7m0e]
    Bed = frappe.qb.DocType("Bed")
    Room = frappe.qb.DocType("Room")
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
            Bed.is_temporary,
            Room.floor.as_("room_floor"),
            Room.room_type.as_("room_type"),
            Room.readiness_status.as_("readiness_status"),
        )
        .where(Bed.building == building)
        .run(as_dict=True)
    )

    # [#3pej3p]
    assignments = frappe.get_all(
        "Housing Assignment",
        filters={
            "building": building,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        },
        fields=["name", "bed", "employee", "employee_name", "party_type", "party", "project", "check_in_date"],
    )
    assignments_by_bed = {a.bed: a for a in assignments}

    # [#5i2m4q]
    tw_names: dict[str, str] = {}
    tw_parties = {a.party for a in assignments if a.party_type == "Temporary Worker" and a.party}
    if tw_parties:
        for row in frappe.get_all(
            "Temporary Worker", filters={"name": ["in", list(tw_parties)]}, fields=["name", "worker_name"]
        ):
            tw_names[row.name] = row.worker_name

    # [#cxv258]
    custody_parents: set[str] = set()
    assignment_names = [a.name for a in assignments]
    if assignment_names:
        custody_rows = frappe.get_all(
            "Accommodation Custody Item",
            filters={
                "parenttype": "Housing Assignment",
                "parent": ["in", assignment_names],
            },
            fields=["parent"],
            distinct=True,
        )
        custody_parents = {c.parent for c in custody_rows}

    # Dominant project per room = the project held by the most active occupants in
    # that room (the Arrivals board tints a room matching the selected worker's
    # project so same-project residents are grouped). Tallied from the bed->room map
    # already loaded above — no extra query.
    bed_to_room = {b.bed: b.room for b in bed_rows}
    room_project_tally: dict[str, dict[str, int]] = {}
    for asg in assignments:
        if not asg.project:
            continue
        room_name = bed_to_room.get(asg.bed)
        if not room_name:
            continue
        room_project_tally.setdefault(room_name, {})
        room_project_tally[room_name][asg.project] = room_project_tally[room_name].get(asg.project, 0) + 1
    dominant_project_by_room = {
        room_name: max(tally, key=tally.get) for room_name, tally in room_project_tally.items()
    }

    # [#ikbfoc]
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
                # [#l1k03s]
                occupant_name = (
                    asg.employee_name
                    or (tw_names.get(asg.party) if asg.party_type == "Temporary Worker" else None)
                    or asg.party
                )
                occupant = {
                    "assignment": asg.name,
                    "employee": asg.employee,
                    "employee_name": occupant_name,
                    "party_type": asg.party_type,
                    "party": asg.party,
                    "project": asg.project,
                    "check_in_date": str(asg.check_in_date) if asg.check_in_date else None,
                    "has_custody": asg.name in custody_parents,
                }

        bed_payload = {
            "bed": bed.bed,
            "bed_code": bed.bed_code,
            "bed_status": bed.bed_status,
            "condition": bed.condition,
            "is_temporary": bed.is_temporary,
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
                "dominant_project": dominant_project_by_room.get(room_name),
                "_floor": bed.room_floor,
                "beds": [],
            }
        rooms_acc[room_name]["beds"].append(bed_payload)

    # [#tdh4h2]
    floors_acc: dict = {}
    for room in rooms_acc.values():
        key = room.pop("_floor")  # [#ewlx1f]
        floors_acc.setdefault(key, []).append(room)

    def _floor_label(n: int) -> str:
        if n == 0:
            return _("Ground Floor")
        if n < 0:
            return _("Basement {0}").format(abs(n))
        return _("Floor {0}").format(n)

    floors = []
    numbered = sorted((k for k in floors_acc if k is not None))
    for floor in numbered:
        rooms_list = sorted(floors_acc[floor], key=lambda r: str(r.get("room_number") or ""))
        floors.append(
            {
                "floor": floor,
                "floor_label": _floor_label(floor),
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


@frappe.whitelist()
def get_buildings_scope_state() -> dict:
    """Explain WHY ``list_supervisor_buildings`` is empty, for a typed empty state.

    Read-only. The list endpoint returns ``[]`` for two very different reasons —
    a building-scoped user with no User-Permission buildings (a permission gap to
    raise with an admin) versus no Active building existing at all. The client
    can't tell them apart from an empty list, so it reads this when the list comes
    back empty. Scope is the same ``permissions`` contract as the list endpoint.

    Returns:
        dict: ``{"is_scoped": bool, "active_buildings": int}``. ``is_scoped`` is
        True when the caller is confined to User-Permission buildings (not an
        oversight role); ``active_buildings`` is the count of Active buildings in
        scope.
    """
    from apex_habitat.habitat import permissions

    is_scoped = not permissions._building_is_unscoped(frappe.session.user)
    f = {"status": "Active"}
    if is_scoped:
        allowed = permissions._allowed_buildings(frappe.session.user)
        if not allowed:
            return {"is_scoped": True, "active_buildings": 0}
        f["name"] = ["in", allowed]
    return {"is_scoped": is_scoped, "active_buildings": frappe.db.count("Building", f)}


@frappe.whitelist()
def list_supervisor_buildings() -> list[dict]:
    """Return the caller's allowed buildings, each with a server-computed bed mix.

    Read-only portfolio header for the Front Desk (one chip per building). Scope
    mirrors the list/card/report contract in ``habitat.permissions``: an unscoped
    oversight role sees every Active building; a building-scoped user sees only
    their User-Permission buildings; a scoped user with none sees ``[]``.

    The bed mix is computed from a BOUNDED set of queries regardless of building
    count — one Active-building query, then ONE bed/room aggregate across all the
    in-scope buildings (no per-building round trip). Each building's counts come
    from the same ``_bed_color`` rules as ``get_building_grid``; the client must
    not recompute color.

    Returns:
        list of ``{building, building_title, total_beds, available, occupied,
        blocked, oos, occupancy_pct}`` sorted by building title.
    """
    # [#scope-mirror] Same scope rule as building_operations_summary._get_buildings:
    # confine a scoped user to their User-Permission buildings; [] when none.
    from apex_habitat.habitat import permissions

    f = {"status": "Active"}
    if not permissions._building_is_unscoped(frappe.session.user):
        allowed = permissions._allowed_buildings(frappe.session.user)
        if not allowed:
            return []
        f["name"] = ["in", allowed]

    buildings = frappe.get_all(
        "Building", filters=f, fields=["name", "building_name"]
    )
    if not buildings:
        return []
    building_names = [b.name for b in buildings]

    # [#one-aggregate] Single bed/room read across every in-scope building, bucketed
    # in Python via _bed_color — bounded no matter how many buildings are in scope.
    Bed = frappe.qb.DocType("Bed")
    Room = frappe.qb.DocType("Room")
    bed_rows = (
        frappe.qb.from_(Bed)
        .left_join(Room)
        .on(Bed.room == Room.name)
        .select(
            Bed.building,
            Bed.status.as_("bed_status"),
            Bed.condition,
            Room.readiness_status,
        )
        .where(Bed.building.isin(building_names))
        .run(as_dict=True)
    )

    mix = {
        name: {"total_beds": 0, "available": 0, "occupied": 0, "blocked": 0, "oos": 0}
        for name in building_names
    }
    for bed in bed_rows:
        bucket = mix.get(bed.building)
        if bucket is None:
            continue
        color = _bed_color(bed.bed_status, bed.condition, bed.readiness_status)
        bucket["total_beds"] += 1
        if color == "green":
            bucket["available"] += 1
        elif color == "red":
            bucket["occupied"] += 1
        elif color == "amber":
            bucket["blocked"] += 1
        else:
            bucket["oos"] += 1

    # Auto-open hint: a single allowed building lets the Front Desk land straight on
    # a loaded board with no Link/chip interaction.
    auto = len(buildings) == 1
    result = []
    for b in buildings:
        m = mix[b.name]
        total = m["total_beds"]
        result.append(
            {
                "building": b.name,
                "building_title": b.building_name or b.name,
                "total_beds": total,
                "available": m["available"],
                "occupied": m["occupied"],
                "blocked": m["blocked"],
                "oos": m["oos"],
                "occupancy_pct": round(m["occupied"] / total * 100) if total else 0,
                "auto": auto,
            }
        )
    result.sort(key=lambda r: str(r["building_title"]))
    return result


# Terminal Resident Request statuses; everything else counts as "open".
_RESIDENT_REQUEST_CLOSED = ("Resolved", "Rejected", "Closed")


def _open_resident_request_statuses() -> list[str]:
    """Open statuses = the Select options minus the terminal set, read from meta
    so a newly-added non-terminal status is automatically treated as open
    (no hand-kept list to drift from the DocType)."""
    options = frappe.get_meta("Resident Request").get_field("status").options or ""
    return [
        o
        for o in (opt.strip() for opt in options.split("\n"))
        if o and o not in _RESIDENT_REQUEST_CLOSED
    ]


@frappe.whitelist()
def building_open_requests(building: str) -> dict:
    """Return the count of OPEN Accommodation Resident Requests for one building.

    Read-only and permission-gated on the building (same gate as
    ``get_building_grid``). "Open" is every status except the terminal set
    (Resolved/Rejected/Closed); the open status list is returned too so the
    client can route to the matching filtered list without hand-keeping it.

    Args:
        building: Accommodation Building docname.

    Returns:
        dict: ``{"building", "open_requests", "statuses"}``.
    """
    frappe.has_permission("Building", "read", doc=building, throw=True)

    statuses = _open_resident_request_statuses()
    count = frappe.db.count(
        "Resident Request",
        filters={"building": building, "status": ["in", statuses]},
    )
    return {"building": building, "open_requests": count, "statuses": statuses}


@frappe.whitelist()
def get_employee_card(employee):
    """Read-only HR identity card for the check-in dialog: name + profile photo.
    Lets the supervisor visually verify the worker before assigning a bed."""
    from apex_habitat.habitat.api.arrivals_desk import _assert_party_in_scope

    frappe.has_permission("Employee", "read", throw=True)
    # [#r7] Mirror the arrivals-desk building scope: a scoped supervisor may look up
    # an UNHOUSED (intake) employee for the pre-assignment check-in, but not one
    # actively housed in another estate — keeps this desk consistent with
    # get_arrival_card and closes the name/photo cross-tenant asymmetry.
    _assert_party_in_scope("Employee", employee)
    vals = frappe.db.get_value("Employee", employee, ["employee_name", "image"], as_dict=True) or {}
    return {"employee_name": vals.get("employee_name"), "image": vals.get("image")}


def _employee_iqama_field() -> str | None:
    """The Employee field that holds the Iqama number, or None if this HR setup
    has none. The field name varies across HR configs, so it is probed from meta
    (same defensive stance Masar uses) rather than hard-coded."""
    meta = frappe.get_meta("Employee")
    for fieldname in ("iqama", "iqama_no", "iqama_number"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def _has_active_assignment(party_type: str, party: str, employee: str | None) -> bool:
    """True if the worker holds a live bed: a submitted Accommodation Assignment
    with no check-out date. Matches on the Employee link when known (the assignment
    is Employee-keyed once linked) else on the party_type/party pair."""
    filters = {"docstatus": 1, "check_out_date": ["is", "not set"]}
    if employee:
        filters["employee"] = employee
    else:
        filters["party_type"] = party_type
        filters["party"] = party
    return bool(frappe.db.exists("Housing Assignment", filters))


# Per-IP throttle matching the Masar read endpoints: a scanned identifier probe
# must not become an Iqama/token-enumeration oracle from one address.
@frappe.whitelist()
@rate_limit(key="frappe.request.remote_addr", limit=60, seconds=60)
def resolve_worker(identifier: str) -> dict:
    """Resolve a scanned identifier to one worker for the Front Desk check-in dialog.

    Accepts either an Iqama number or a scanned personal Masar token and returns
    the single matching worker, so the supervisor can confirm-and-go instead of
    typing an Employee link. Read-only — no posting, locking, or document writes.

    Resolution order (first match wins): the unique Masar token, then the Iqama on
    Employee (only when this HR setup exposes an Iqama field), then a Temporary
    Worker's Iqama (surfacing its linked permanent Employee when one exists).

    Permission: gated on ``Employee`` read (the same gate as
    ``get_employee_card``); a Temporary Worker result additionally requires
    ``Temporary Worker`` read so it cannot leak across DocType permissions.

    Args:
        identifier: an Iqama number or a scanned Masar token.

    Returns:
        dict ``{found, party_type, party, employee, employee_name, image,
        has_active_assignment, message}``. ``found`` is False with a message when
        nothing matches.
    """
    frappe.has_permission("Employee", "read", throw=True)

    identifier = (identifier or "").strip()
    if not identifier:
        return {"found": False, "message": _("Enter or scan an Iqama number or worker link.")}

    party_type = party = employee = employee_name = image = None

    # A Masar token is unique and unguessable; resolve it exactly first.
    token_row = frappe.db.get_value(
        "Masar Worker Token",
        {"token": identifier, "enabled": 1},
        ["party_type", "party", "employee", "employee_name"],
        as_dict=True,
    )
    if token_row:
        party_type = token_row.party_type
        party = token_row.party
        employee = token_row.employee
        employee_name = token_row.employee_name

    # Otherwise treat the identifier as an Iqama: Employee first (if this HR setup
    # has an Iqama field), then Temporary Worker.
    if not party:
        iqama_field = _employee_iqama_field()
        if iqama_field:
            emp = frappe.db.get_value(
                "Employee",
                {iqama_field: identifier, "status": ["not in", ("Inactive", "Left")]},
                ["name", "employee_name"],
                as_dict=True,
            )
            if emp:
                party_type, party, employee, employee_name = "Employee", emp.name, emp.name, emp.employee_name

    if not party:
        tw = frappe.db.get_value(
            "Temporary Worker",
            {"iqama_number": identifier},
            ["name", "worker_name", "linked_employee"],
            as_dict=True,
        )
        if tw:
            party_type, party, employee_name = "Temporary Worker", tw.name, tw.worker_name
            employee = tw.linked_employee or None

    if not party:
        return {"found": False, "message": _("No worker matches {0}.").format(identifier)}

    # Don't leak Temporary Worker identity to a caller without that read grant.
    if party_type == "Temporary Worker":
        frappe.has_permission("Temporary Worker", "read", throw=True)

    if employee:
        image = frappe.db.get_value("Employee", employee, "image")
        if not employee_name:
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")

    return {
        "found": True,
        "party_type": party_type,
        "party": party,
        "employee": employee,
        "employee_name": employee_name,
        "image": image,
        "has_active_assignment": _has_active_assignment(party_type, party, employee),
        "message": None,
    }


@frappe.whitelist(methods=["POST"])
def set_room_readiness(room, status):
    """Set Accommodation Room.readiness_status from the Front Desk board.

    A plain field write — NO posting, locking, or ledger logic. The Select value
    is validated against the field's own options (read from meta, never a
    hand-kept list) so it can't drift from the DocType. Permission is the
    document-level ``write`` grant on Accommodation Room (checked below; a
    read-only role such as Resident Supervisor is refused).

    Args:
        room: Accommodation Room docname.
        status: one of the readiness_status Select options.

    Returns:
        dict: ``{"room": <docname>, "readiness_status": <status>}``.
    """
    frappe.has_permission("Room", "write", doc=room, throw=True)

    options = frappe.get_meta("Room").get_field("readiness_status").options or ""
    valid = [o for o in (opt.strip() for opt in options.split("\n")) if o]
    if status not in valid:
        frappe.throw(_("{0} is not a valid readiness status.").format(status))

    frappe.db.set_value("Room", room, "readiness_status", status)
    return {"room": room, "readiness_status": status}


@frappe.whitelist(methods=["POST"])
def quick_check_in(bed, employee=None, project=None, check_in_date=None,
                   cost_center=None, assignment_type="New Assignment",
                   room_condition_snapshot=None, party_type=None, party=None,
                   terms_signature=None):
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
        terms_signature: optional housing-terms acceptance signature data-URI
            captured on the tablet; stamps ``terms_accepted_on`` when present.

    Returns:
        dict: ``{"assignment": <docname>, "bed": <bed>}``.
    """
    frappe.has_permission("Housing Assignment", "create", throw=True)
    frappe.has_permission("Housing Assignment", "submit", throw=True)

    # [#r8vwzx]
    if not party and employee:
        party_type, party = "Employee", employee

    room, building = frappe.db.get_value("Bed", bed, ["room", "building"])
    if not room or not building:
        frappe.throw(_("Bed {0} is not linked to a room and building.").format(bed))

    doc = frappe.get_doc(
        {
            "doctype": "Housing Assignment",
            "bed": bed,
            "room": room,
            "building": building,
            "party_type": party_type,
            "party": party,
            "project": project,
            "check_in_date": check_in_date,
            "cost_center": cost_center,
            "assignment_type": assignment_type or "New Assignment",
            "room_condition_snapshot": room_condition_snapshot,
            "terms_signature": terms_signature or None,
            "terms_accepted_on": now() if terms_signature else None,
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {
        "assignment": doc.name,
        "bed": bed,
        "party_type": doc.party_type,
        "party": doc.party,
        "employee": doc.employee,
    }


@frappe.whitelist(methods=["POST"])
def quick_check_out(bed, checkout_date=None, checkout_reason=None, room_condition_snapshot=None):
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
    frappe.has_permission("Housing Checkout", "create", throw=True)
    frappe.has_permission("Housing Checkout", "submit", throw=True)

    assignment = frappe.db.get_value(
        "Housing Assignment",
        {"bed": bed, "docstatus": 1, "check_out_date": ["is", "not set"]},
        "name",
    )
    if not assignment:
        frappe.throw(_("No active assignment found for bed {0}.").format(bed))

    # [#f8dq4j]
    has_custody = bool(
        frappe.db.exists(
            "Accommodation Custody Item",
            {"parenttype": "Housing Assignment", "parent": assignment},
        )
    )
    if has_custody:
        return {"requires_full_form": True, "assignment": assignment}

    doc = frappe.get_doc(
        {
            "doctype": "Housing Checkout",
            "assignment": assignment,
            "checkout_date": checkout_date or today(),
            "checkout_reason": checkout_reason,
            "room_condition_snapshot": room_condition_snapshot,
        }
    )
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"checkout": doc.name, "bed": bed}
