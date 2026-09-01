# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now, today

from apex.apex_core.utils.portal_identity import hash_token
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.habitat.doctype.housing_checkout.housing_checkout import _outstanding_custody_for_party
from apex.habitat.utils import occupancy
from apex.habitat.utils.housing_scope import active_building_scope, assert_party_in_scope
from apex.salis.api.driver_portal.images import verified_image_type


def _floor_label(n: int) -> str:
    if n == 0:
        return _("Ground Floor")
    if n < 0:
        return _("Basement {0}").format(abs(n))
    return _("Floor {0}").format(n)


def _grid_bed_rows(building: str) -> list:
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
    tw_parties = {a.party for a in assignments if a.party_type == "Temporary Worker" and a.party}
    if not tw_parties:
        return {}
    rows = frappe.get_list(
        "Temporary Worker", filters={"name": ["in", list(tw_parties)]},
        fields=["name", "worker_name"]
    )
    return {row.name: row.worker_name for row in rows}


def _assignments_holding_custody(assignments) -> set:
    employees = {a.employee for a in assignments if a.employee}
    if not employees:
        return set()
    balances: dict[str, float] = {}
    for row in frappe.get_list(
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
    frappe.has_permission("Building", "read", doc=building, throw=True)

    building_title = frappe.db.get_value("Building", building, "building_name") or building

    rooms = frappe.get_list(
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
        limit_page_length=0,
    )
    rooms_by_name = {r.name: r for r in rooms}

    bed_rows = _grid_bed_rows(building)

    assignments = frappe.get_list(
        "Housing Assignment",
        filters=occupancy.active_assignment_filters(building=building),
        fields=["name", "bed", "employee", "employee_name", "party_type", "party", "project", "check_in_date"],
        limit_page_length=0,
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
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return {"is_scoped": True, "active_buildings": 0}
    return {
        "is_scoped": scope.is_scoped,
        "active_buildings": frappe.db.count("Building", scope.filters),
    }


@frappe.whitelist()
def list_supervisor_buildings() -> list[dict]:
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return []

    buildings = frappe.get_list(
        "Building",
        filters=scope.filters,
        fields=["name", "building_name", "site", "accommodation_type"],
        limit_page_length=0,
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
    if not sites:
        return {}
    rows = frappe.get_all(
        "Site", filters={"name": ["in", list(sites)]}, fields=["name", "site_name"]
    )
    return {row.name: row.site_name or row.name for row in rows}


_RESIDENT_REQUEST_CLOSED = ("Resolved", "Rejected", "Closed")


def _open_resident_request_statuses() -> list[str]:
    options = frappe.get_meta("Resident Request").get_field("status").options or ""
    return [
        o
        for o in (opt.strip() for opt in options.split("\n"))
        if o and o not in _RESIDENT_REQUEST_CLOSED
    ]


@frappe.whitelist()
def building_open_requests(building: str) -> dict:
    frappe.has_permission("Building", "read", doc=building, throw=True)

    statuses = _open_resident_request_statuses()
    count = frappe.db.count(
        "Resident Request",
        filters={"building": building, "status": ["in", statuses]},
    )
    return {"building": building, "open_requests": count, "statuses": statuses}


@frappe.whitelist()
def get_employee_card(employee):
    frappe.has_permission("Employee", "read", throw=True)
    assert_party_in_scope("Employee", employee)
    vals = frappe.db.get_value("Employee", employee, ["employee_name", "image"], as_dict=True) or {}
    return {"employee_name": vals.get("employee_name"), "image": vals.get("image")}


def _employee_iqama_field() -> str | None:
    meta = frappe.get_meta("Employee")
    for fieldname in ("iqama", "iqama_no", "iqama_number"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def _has_active_assignment(party_type: str, party: str, employee: str | None) -> bool:
    filters = occupancy.active_assignment_filters()
    if employee:
        filters["employee"] = employee
    else:
        filters["party_type"] = party_type
        filters["party"] = party
    return bool(frappe.db.exists("Housing Assignment", filters))


def _match_masar_token(identifier):
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

    assert_party_in_scope(party_type, party)

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

    assert_party_in_scope(party_type, party)

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
