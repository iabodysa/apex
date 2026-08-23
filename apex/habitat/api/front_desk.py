# Copyright (c) 2026, afmcoltd
"""Front Desk visual bed board API.

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

Active-occupancy semantics, the bed colour rule and the bed mix come from
``habitat.utils.occupancy``, shared with the Arrivals Desk.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now, today

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.habitat.utils import occupancy
from apex.habitat.utils.housing_scope import active_building_scope
from apex.salis.api.driver_portal.images import verified_image_type


def _floor_label(n: int) -> str:
    """Human floor name from a floor number: 0 is the ground floor, negatives are
    basements counted downwards."""
    if n == 0:
        return _("Ground Floor")
    if n < 0:
        return _("Basement {0}").format(abs(n))
    return _("Floor {0}").format(n)


def _grid_bed_rows(building: str) -> list:
    """Every bed in one building with the room facts the board draws it from, in ONE
    join rather than a lookup per bed.

    Built with ``frappe.qb`` (frappe/query_builder) because the one thing
    ``frappe.get_all`` cannot do is LEFT JOIN a sibling DocType: fetching beds and
    then reading each bed's room is one query per bed, and a large building draws its
    board hundreds of times over.
    """
    Bed = frappe.qb.DocType("Bed")
    Room = frappe.qb.DocType("Room")
    return (
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


def _temporary_worker_names(assignments) -> dict:
    """Display names for the Temporary Worker occupants, in one query or none."""
    tw_parties = {a.party for a in assignments if a.party_type == "Temporary Worker" and a.party}
    if not tw_parties:
        return {}
    rows = frappe.get_all(
        "Temporary Worker", filters={"name": ["in", list(tw_parties)]},
        fields=["name", "worker_name"]
    )
    return {row.name: row.worker_name for row in rows}


def _assignments_holding_custody(assignments) -> set:
    """Which of these assignments belong to a resident who still holds custody.

    ONE definition serves the board, the quick-checkout guard and the checkout gate:
    the net Accommodation Stock Ledger balance, which is what
    ``housing_checkout._outstanding_custody_for_employee`` reads and what the stock
    balance report and the value-at-risk card already use. Checking instead whether the
    assignment carries any Accommodation Custody Item child row would break this: those
    rows are written by the desk form and cleared by nothing, so a resident who returned
    everything would stay blocked for ever.

    One bulk query regardless of occupancy: the ledger is read once for every
    employee on the board, never per bed.
    """
    employees = {a.employee for a in assignments if a.employee}
    if not employees:
        return set()
    balances: dict[str, float] = {}
    for row in frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "is_cancelled": 0,
            "item_type": "Custody Article",
            "employee": ["in", list(employees)],
        },
        fields=["employee", "signed_qty"],
    ):
        balances[row.employee] = balances.get(row.employee, 0) + (row.signed_qty or 0)
    holding = {emp for emp, qty in balances.items() if qty > 0}
    return {a.name for a in assignments if a.employee in holding}


def _dominant_project_by_room(assignments, bed_to_room) -> dict:
    """The project most of a room's occupants belong to, so the board can colour a
    room by crew. Ties resolve to whichever project ``max`` sees first."""
    room_project_tally: dict[str, dict[str, int]] = {}
    for asg in assignments:
        if not asg.project:
            continue
        room_name = bed_to_room.get(asg.bed)
        if not room_name:
            continue
        room_project_tally.setdefault(room_name, {})
        room_project_tally[room_name][asg.project] = room_project_tally[room_name].get(asg.project, 0) + 1
    return {
        room_name: max(tally, key=tally.get) for room_name, tally in room_project_tally.items()
    }


def _occupant_payload(asg, tw_names, custody_parents) -> dict:
    """The occupant block on a red bed. A Temporary Worker has no ``employee_name``,
    so his own worker name stands in; the party id is the last resort."""
    occupant_name = (
        asg.employee_name
        or (tw_names.get(asg.party) if asg.party_type == "Temporary Worker" else None)
        or asg.party
    )
    return {
        "assignment": asg.name,
        "employee": asg.employee,
        "employee_name": occupant_name,
        "party_type": asg.party_type,
        "party": asg.party,
        "project": asg.project,
        "check_in_date": str(asg.check_in_date) if asg.check_in_date else None,
        "has_custody": asg.name in custody_parents,
    }


def _bed_payload(bed, color, occupant) -> dict:
    """One bed as the board draws it. ``bed_color`` is server-computed; the client
    must not recompute it."""
    return {
        "bed": bed.bed,
        "bed_code": bed.bed_code,
        "bed_status": bed.bed_status,
        "condition": bed.condition,
        "is_temporary": bed.is_temporary,
        "bed_color": color,
        "occupant": occupant,
    }


def _room_shell(bed, room_meta, dominant_project) -> dict:
    """The room a bed sits in, before its beds are attached. Room facts come from the
    Room record where there is one; the bed's own joined columns stand in when the
    room row is missing, so an orphaned bed still renders."""
    return {
        "room": bed.room,
        "room_number": room_meta.room_number if room_meta else bed.room,
        "room_type": bed.room_type,
        "readiness_status": bed.readiness_status,
        "room_status": room_meta.status if room_meta else None,
        "bed_capacity": room_meta.bed_capacity if room_meta else None,
        "current_occupancy": room_meta.current_occupancy if room_meta else None,
        "dominant_project": dominant_project,
        "_floor": bed.room_floor,
        "beds": [],
    }


def _rooms_into_floors(rooms_acc) -> list:
    """Group the accumulated rooms into ordered floors. Rooms whose floor is unset
    land in a trailing Unassigned Floor rather than being dropped."""
    floors_acc: dict = {}
    for room in rooms_acc.values():
        key = room.pop("_floor")
        floors_acc.setdefault(key, []).append(room)

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
    return floors


@frappe.whitelist()
def get_building_grid(building: str) -> dict:
    """Return the floor -> room -> bed grid for one building for the Front Desk board.

    Reads only. Permission-gated on the building. Built from a BOUNDED set of
    bulk queries (no per-bed or per-room round trips). Each bed gets a
    server-computed ``bed_color`` (see ``occupancy.bed_color``); the client must not
    recompute color.

    Args:
        building: Accommodation Building docname (source of truth).

    Returns:
        dict shaped as ``{building, building_title, generated_on, summary, floors}``.
    """
    frappe.has_permission("Building", "read", doc=building, throw=True)

    building_title = frappe.db.get_value("Building", building, "building_name") or building

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

    bed_rows = _grid_bed_rows(building)

    assignments = frappe.get_all(
        "Housing Assignment",
        filters=occupancy.active_assignment_filters(building=building),
        fields=["name", "bed", "employee", "employee_name", "party_type", "party", "project", "check_in_date"],
    )
    assignments_by_bed = {a.bed: a for a in assignments}

    tw_names = _temporary_worker_names(assignments)
    custody_parents = _assignments_holding_custody(assignments)

    bed_to_room = {b.bed: b.room for b in bed_rows}
    dominant_project_by_room = _dominant_project_by_room(assignments, bed_to_room)

    summary = occupancy.empty_bed_mix()
    rooms_acc: dict[str, dict] = {}

    for bed in bed_rows:
        color = occupancy.bed_color(bed.bed_status, bed.condition, bed.readiness_status)
        occupancy.tally_bed(summary, color)

        occupant = None
        if color == "red":
            asg = assignments_by_bed.get(bed.bed)
            if asg:
                occupant = _occupant_payload(asg, tw_names, custody_parents)

        room_name = bed.room
        if room_name not in rooms_acc:
            rooms_acc[room_name] = _room_shell(
                bed, rooms_by_name.get(room_name), dominant_project_by_room.get(room_name)
            )
        rooms_acc[room_name]["beds"].append(_bed_payload(bed, color, occupant))

    return {
        "building": building,
        "building_title": building_title,
        "generated_on": now(),
        "summary": summary,
        "floors": _rooms_into_floors(rooms_acc),
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
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return {"is_scoped": True, "active_buildings": 0}
    return {
        "is_scoped": scope.is_scoped,
        "active_buildings": frappe.db.count("Building", scope.filters),
    }


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
    from the same ``occupancy.bed_color`` rules as ``get_building_grid``; the client
    must not recompute color.

    Returns:
        list of ``{building, building_title, total_beds, available, occupied,
        blocked, oos, occupancy_pct}`` sorted by building title.
    """
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return []

    buildings = frappe.get_all(
        "Building",
        filters=scope.filters,
        fields=["name", "building_name", "site", "accommodation_type"],
    )
    if not buildings:
        return []
    building_names = [b.name for b in buildings]

    mix = occupancy.bed_mix(occupancy.bed_mix_rows(building_names), building_names)
    site_titles = _site_titles({b.site for b in buildings if b.site})

    auto = len(buildings) == 1
    result = []
    for b in buildings:
        m = mix[b.name]
        total = m["total_beds"]
        result.append(
            {
                "building": b.name,
                "building_title": b.building_name or b.name,
                "site": b.site,
                "site_title": site_titles.get(b.site) or b.site,
                "accommodation_type": b.accommodation_type,
                "has_rooms": bool(total),
                "total_beds": total,
                "available": m["available"],
                "occupied": m["occupied"],
                "blocked": m["blocked"],
                "oos": m["out_of_service"],
                "occupancy_pct": round(m["occupied"] / total * 100) if total else 0,
                "auto": auto,
            }
        )
    result.sort(key=lambda r: (str(r["site_title"] or ""), str(r["building_title"])))
    return result


def _site_titles(sites: set) -> dict:
    """Docname to display title for the Sites the caller's buildings sit under."""
    if not sites:
        return {}
    rows = frappe.get_all(
        "Site", filters={"name": ["in", list(sites)]}, fields=["name", "site_name"]
    )
    return {row.name: row.site_name or row.name for row in rows}


_RESIDENT_REQUEST_CLOSED = ("Resolved", "Rejected", "Closed")


def _open_resident_request_statuses() -> list[str]:
    """Open statuses = the Select options minus the terminal set, read from meta
    so a newly-added non-terminal status is automatically treated as open
    (no hand-kept list to drift from the DocType).

    ``frappe.get_meta(...).get_field`` (frappe/model/meta.py:66, :242) supplies the
    options. Only the TERMINAL set is named here, because that is the shorter and more
    stable half: a status added to the DocType is open until someone decides it ends
    the request, and defaulting the other way would silently close it.
    """
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
    from apex.habitat.api.arrivals_desk import _assert_party_in_scope

    frappe.has_permission("Employee", "read", throw=True)
    _assert_party_in_scope("Employee", employee)
    vals = frappe.db.get_value("Employee", employee, ["employee_name", "image"], as_dict=True) or {}
    return {"employee_name": vals.get("employee_name"), "image": vals.get("image")}


def _employee_iqama_field() -> str | None:
    """The Employee field that holds the Iqama number, or None if this HR setup
    has none. The field name varies across HR configs, so it is probed from meta
    (same defensive stance Masar uses) rather than hard-coded.

    ``frappe.get_meta(...).has_field`` (frappe/model/meta.py:66, :247) answers whether
    a name exists on this site. The one thing it cannot do is tell which of several
    candidate names means Iqama, so the order here is the decision — the first match
    wins, and a site carrying two of them gets the first in this list.
    """
    meta = frappe.get_meta("Employee")
    for fieldname in ("iqama", "iqama_no", "iqama_number"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def _has_active_assignment(party_type: str, party: str, employee: str | None) -> bool:
    """True if the worker holds a live bed: a submitted Accommodation Assignment
    with no check-out date. Matches on the Employee link when known (the assignment
    is Employee-keyed once linked) else on the party_type/party pair."""
    filters = occupancy.active_assignment_filters()
    if employee:
        filters["employee"] = employee
    else:
        filters["party_type"] = party_type
        filters["party"] = party
    return bool(frappe.db.exists("Housing Assignment", filters))


def _match_masar_token(identifier):
    """``(party_type, party, employee, employee_name)`` for a scanned personal Masar
    link, or None. The raw token is never stored, so the lookup is on its hash."""
    from apex.apex_core.utils.portal_identity import hash_token

    row = frappe.db.get_value(
        "Masar Worker Token",
        {"token": hash_token(identifier), "enabled": 1},
        ["party_type", "party", "employee", "employee_name"],
        as_dict=True,
    )
    if not row:
        return None
    return row.party_type, row.party, row.employee, row.employee_name


def _match_employee_iqama(identifier):
    """``(party_type, party, employee, employee_name)`` for an Iqama on a working
    Employee, or None. Returns None outright when this HR setup exposes no Iqama
    field at all."""
    iqama_field = _employee_iqama_field()
    if not iqama_field:
        return None
    emp = frappe.db.get_value(
        "Employee",
        {iqama_field: identifier, "status": ["not in", ("Inactive", "Left")]},
        ["name", "employee_name"],
        as_dict=True,
    )
    if not emp:
        return None
    return "Employee", emp.name, emp.name, emp.employee_name


def _match_temporary_worker_iqama(identifier):
    """``(party_type, party, employee, employee_name)`` for an Iqama on a Temporary
    Worker, or None. Surfaces his linked permanent Employee when one exists."""
    tw = frappe.db.get_value(
        "Temporary Worker",
        {"iqama_number": identifier},
        ["name", "worker_name", "linked_employee"],
        as_dict=True,
    )
    if not tw:
        return None
    return "Temporary Worker", tw.name, tw.linked_employee or None, tw.worker_name


@frappe.whitelist()
@rate_limit(limit=60, seconds=60)
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
    ``Temporary Worker`` read so it cannot leak across DocType permissions. The
    resolved party is then put through the SAME per-doc building gate as
    ``get_employee_card`` — a type-level read only proves the caller may read the
    doctype, not that the worker belongs to their estate, and every lookup below
    is a ``db.get_value`` that bypasses ``permission_query_conditions``.

    Args:
        identifier: an Iqama number or a scanned Masar token.

    Returns:
        dict ``{found, party_type, party, employee, employee_name, image,
        has_active_assignment, message}``. ``found`` is False with a message when
        nothing matches.
    """
    if not frappe.has_permission("Employee", "select") and not frappe.has_permission(
        "Employee", "read"
    ):
        frappe.throw(
            _("You are not allowed to look up workers."), frappe.PermissionError
        )

    identifier = (identifier or "").strip()
    if not identifier:
        return {"found": False, "message": _("Enter or scan an Iqama number or worker link.")}

    match = (
        _match_masar_token(identifier)
        or _match_employee_iqama(identifier)
        or _match_temporary_worker_iqama(identifier)
    )
    if not match:
        return {"found": False, "message": _("No worker matches {0}.").format(identifier)}

    party_type, party, employee, employee_name = match
    image = None

    if party_type == "Temporary Worker":
        frappe.has_permission("Temporary Worker", "read", throw=True)

    from apex.habitat.api.arrivals_desk import _assert_party_in_scope

    _assert_party_in_scope(party_type, party)

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


@frappe.whitelist()
def describe_worker(party_type: str, party: str) -> dict:
    """Resolve a worker the caller already identified into the check-in payload.

    ``resolve_worker`` answers for a SCAN; this answers for a party the caller
    already holds, which is what a screen navigating from the arrivals list has.
    It returns the same shape, computed the same way, so no client has to invent
    ``has_active_assignment`` or ``employee`` — values only the server can know.
    Same gates: the ``select`` or ``read`` pair a Link picker accepts, the
    Temporary Worker read grant, and the per-doc estate scope.
    """
    if not frappe.has_permission("Employee", "select") and not frappe.has_permission(
        "Employee", "read"
    ):
        frappe.throw(_("You are not allowed to look up workers."), frappe.PermissionError)

    party_type = (party_type or "").strip()
    party = (party or "").strip()
    if party_type not in ("Employee", "Temporary Worker") or not party:
        return {"found": False, "message": _("No worker matches {0}.").format(party or "")}

    if party_type == "Temporary Worker":
        frappe.has_permission("Temporary Worker", "read", throw=True)

    from apex.habitat.api.arrivals_desk import _assert_party_in_scope

    _assert_party_in_scope(party_type, party)

    if party_type == "Employee":
        employee = party
        employee_name, image = (
            frappe.db.get_value("Employee", party, ["employee_name", "image"]) or (None, None)
        )
    else:
        tw = frappe.db.get_value(
            "Temporary Worker", party, ["linked_employee", "worker_name"], as_dict=True
        )
        employee = (tw or {}).get("linked_employee") or None
        employee_name = (tw or {}).get("worker_name")
        image = frappe.db.get_value("Employee", employee, "image") if employee else None

    if not employee_name:
        return {"found": False, "message": _("No worker matches {0}.").format(party)}

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

    if not party and employee:
        party_type, party = "Employee", employee

    check_in_date = check_in_date or today()

    terms_signature = (terms_signature or "").strip()
    if terms_signature:
        verified_image_type(terms_signature)

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

    row = frappe.db.get_value(
        "Housing Assignment",
        occupancy.active_assignment_filters(bed=bed),
        ["name", "employee", "party_type", "party"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("No active assignment found for bed {0}.").format(bed))
    assignment = row.name

    from apex.habitat.doctype.housing_checkout.housing_checkout import (
        _outstanding_custody_for_party,
    )

    if _outstanding_custody_for_party(
        row.party_type, row.party, row.employee
    ):
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
