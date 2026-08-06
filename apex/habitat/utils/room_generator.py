# Copyright (c) 2026, AFMCO and contributors
"""The floor-plan room/bed generator.

The generator turns a building's floor_plan rows into Accommodation Room and Bed
records, idempotently: it never deletes, it reconciles what already exists, and it
refuses to grow a building silently. This module owns every part of that except the
whitelisted entry point, which stays on the Building controller.

Room numbering (``room_number`` / ``floor_code``), floor ordering, and the operator
summary take plain values and return values, so the naming and reporting rules are
exercisable without a bench.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.utils import today

from apex.habitat.utils import building_rollup, occupancy


class GenerationStats:
    """Mutable accumulator threaded through the generator's per-row helpers so the
    running counts fold in one place; the summary is built from it at the end."""

    def __init__(self):
        self.created_rooms = 0
        self.updated_rooms = 0
        self.skipped_rooms = 0
        self.pending_new_rooms = 0
        self.created_beds = 0
        self.skipped_beds = 0
        self.pending_new_beds = 0
        self.row_failures: list = []
        self.pending_capacity_reductions = 0
        self.retired_beds = 0
        self.blocked_reductions: list = []


def room_number(abbreviation, floor_code_value, prefix, seq):
    """Room number ``{abbr}-{floor_code}{prefix}{seq:02d}``. A blank prefix yields the
    historical ``{abbr}-{floor_code}{seq:02d}`` byte-for-byte (no renumbering), so the
    prefix only ever ADDS a wing/block segment (e.g. ``JED1-GA01``) for non-blank rows."""
    prefix = (prefix or "").strip()
    return f"{abbreviation}-{floor_code_value}{prefix}{seq:02d}"


def floor_code(floor_type, floor_num):
    """Floor code used in room numbers, driven by the floor's classification so the
    type is FUNCTIONAL, not cosmetic: Basement -> B<n> (below ground), Ground -> G,
    Roof -> R, Middle/unspecified -> the numeric floor."""
    ft = (floor_type or "").strip()
    if ft == "Basement":
        return f"B{floor_num}" if floor_num else "B"
    if ft == "Ground":
        return "G"
    if ft == "Roof":
        return f"R{floor_num}" if floor_num and floor_num > 1 else "R"
    return "G" if floor_num == 0 else str(floor_num)


def floor_sort_key(row):
    """Order floors bottom-to-top by classification: Basement -> Ground -> Middle -> Roof."""
    priority = {"Basement": 0, "Ground": 1, "Roof": 3}
    return (priority.get((row.floor_type or "").strip(), 2), int(row.floor_number or 0))


def validate_floor_plan(doc):
    """Floor-plan preconditions: at least one row, and no two floors collapsing to the
    same floor code (which would mint identical room numbers). [#caqr8g]"""
    if not doc.floor_plan:
        frappe.throw(_("No floor plan defined. Add floor rows before generating."))

    _seen_floor_codes: dict[str, int] = {}
    for _row in doc.floor_plan:
        _fc = floor_code(_row.floor_type, int(_row.floor_number or 0))
        _fn = int(_row.floor_number or 0)
        if _fc in _seen_floor_codes:
            frappe.throw(
                _("Floor plan conflict: floor {0} and floor {1} both produce floor code \"{2}\". "
                  "Two floors cannot share the same code — they would generate identical room numbers. "
                  "Assign distinct floor numbers or floor types.").format(
                    _seen_floor_codes[_fc], _fn, _fc
                ),
                title=_("Duplicate Floor Code"),
            )
        _seen_floor_codes[_fc] = _fn


def load_existing(building_name):
    """Pre-load the building's existing rooms (room_number -> name) and bed codes so the
    generator stays idempotent without per-iteration lookups. [#jcmjsz][#fkd615]"""
    existing_room_rows = frappe.db.get_all(
        "Room",
        filters={"building": building_name},
        fields=["name", "room_number"],
    )
    existing_room_map = {r.room_number: r.name for r in existing_room_rows}

    Bed = DocType("Bed")
    Room = DocType("Room")
    _bed_rows = (
        frappe.qb.from_(Bed)
        .join(Room)
        .on(Bed.room == Room.name)
        .where(Room.building == building_name)
        .select(Bed.bed_code)
        .run(as_list=True)
    )
    existing_bed_codes = {r[0] for r in _bed_rows}
    return existing_room_map, existing_bed_codes


def _apply_capacity_reductions(room_number_value, capacity, old_cap, existing_bed_codes, stats):
    """Retire the surplus beds when a room's planned capacity drops (confirmed path).
    Sets each unoccupied, non-temporary surplus bed Out of Service; an occupied one blocks
    the reduction. Returns True when the bed_capacity may be lowered (none blocked). [#ea5tqj]"""
    _surplus_blocked = 0
    for _b_idx in range(capacity + 1, old_cap + 1):
        _surplus_code = f"{room_number_value}-B{_b_idx:02d}"
        if not frappe.db.exists("Bed", _surplus_code):
            continue
        _is_temp = frappe.db.get_value("Bed", _surplus_code, "is_temporary")
        if _is_temp:
            continue
        _occupied = frappe.db.exists(
            "Housing Assignment",
            occupancy.active_assignment_filters(bed=_surplus_code),
        )
        if _occupied:
            _surplus_blocked += 1
        else:
            frappe.db.set_value("Bed", _surplus_code, "status", "Out of Service")
            existing_bed_codes.discard(_surplus_code)
            stats.retired_beds += 1
    if _surplus_blocked:
        stats.blocked_reductions.append(
            _("{0}: {1} occupied bed(s) prevented capacity reduction.").format(
                room_number_value, _surplus_blocked)
        )
        return False
    return True


def _reconcile_existing_room(room_doc_name, room_number_value, rtype, capacity,
                             confirm_capacity_reduction, existing_bed_codes, stats):
    """Bring one existing room in line with the plan: update room_type and bed_capacity.
    A capacity INCREASE applies directly; a DECREASE needs confirmation and surplus-bed
    retirement (delegated to _apply_capacity_reductions). [#h26quk][#trx8ab]"""
    current = frappe.db.get_value(
        "Room", room_doc_name,
        ["room_type", "bed_capacity"], as_dict=True,
    )
    updates = {}
    if current and current.room_type != rtype:
        updates["room_type"] = rtype
    if current and (current.bed_capacity or 0) != capacity:
        old_cap = int(current.bed_capacity or 0)
        if capacity >= old_cap:
            updates["bed_capacity"] = capacity
        elif not confirm_capacity_reduction:
            stats.pending_capacity_reductions += 1
        elif _apply_capacity_reductions(room_number_value, capacity, old_cap,
                                        existing_bed_codes, stats):
            updates["bed_capacity"] = capacity
    if updates:
        frappe.db.set_value("Room", room_doc_name, updates)
        stats.updated_rooms += 1
    else:
        stats.skipped_rooms += 1


def _create_room(building_name, room_number_value, floor_num, rtype, capacity,
                 existing_room_map, stats):
    """Insert a NEW room from the plan and register it in the room map. Returns its name,
    or None when the insert failed (recorded as a row failure). [#4cp8q8]"""
    try:
        room = frappe.get_doc({
            "doctype": "Room",
            "building": building_name,
            "room_number": room_number_value,
            "floor": floor_num,
            "room_type": rtype,
            "bed_capacity": capacity,
            "status": "Available",
            "readiness_status": "Unknown",
        })
        room.insert(ignore_permissions=False)
        existing_room_map[room_number_value] = room.name
        stats.created_rooms += 1
        return room.name
    except Exception as exc:
        stats.row_failures.append(_("Room {0}: {1}").format(room_number_value, str(exc)))
        return None


def _generate_beds_for_room(room_doc_name, room_number_value, capacity, allow_create,
                            existing_bed_codes, stats):
    """Mint the room's beds (codes ``{room}-B01..``), skipping any that already exist; when
    new beds are not yet permitted they are counted pending, not created. [#gzcnzc]"""
    for b in range(1, capacity + 1):
        bed_code = f"{room_number_value}-B{b:02d}"
        if bed_code in existing_bed_codes:
            stats.skipped_beds += 1
        elif not allow_create:
            stats.pending_new_beds += 1
        else:
            try:
                bed = frappe.get_doc({
                    "doctype": "Bed",
                    "room": room_doc_name,
                    "bed_code": bed_code,
                    "status": "Available",
                    "condition": "Good",
                })
                bed.insert(ignore_permissions=False)
                existing_bed_codes.add(bed_code)
                stats.created_beds += 1
            except Exception as exc:
                stats.row_failures.append(_("Bed {0}: {1}").format(bed_code, str(exc)))


def process_floor_row(row, abbreviation, building_name, allow_create,
                      confirm_capacity_reduction, existing_room_map, existing_bed_codes, stats):
    """Generate/reconcile every room (and its beds) for one floor-plan row, in seq order."""
    floor_num = int(row.floor_number or 0)
    floor_code_value = floor_code(row.floor_type, floor_num)
    start = int(row.starting_room_number or 1)
    count = int(row.room_count or 0)
    capacity = int(row.bed_capacity_per_room or 0)
    rtype = row.room_type or "Standard"
    gen_beds = int(row.generate_beds or 0)

    if count <= 0:
        return
    if gen_beds and capacity <= 0:
        frappe.throw(
            _("Beds per Room must be greater than 0 when Auto-Generate Beds is enabled. Floor {0}, type {1}.").format(floor_num, rtype)
        )
    if gen_beds and capacity > 50:
        frappe.throw(
            _("Bed capacity per room exceeds maximum of 50. Floor {0}: {1} beds configured.").format(floor_num, capacity)
        )

    prefix = (row.room_prefix or "").strip()
    for i in range(count):
        seq = start + i
        room_number_value = room_number(abbreviation, floor_code_value, prefix, seq)

        if room_number_value in existing_room_map:
            room_doc_name = existing_room_map[room_number_value]
            _reconcile_existing_room(
                room_doc_name, room_number_value, rtype, capacity,
                confirm_capacity_reduction, existing_bed_codes, stats,
            )
        elif not allow_create:
            stats.pending_new_rooms += 1
            continue
        else:
            room_doc_name = _create_room(
                building_name, room_number_value, floor_num, rtype, capacity,
                existing_room_map, stats
            )
            if room_doc_name is None:
                continue

        if gen_beds and room_doc_name:
            _generate_beds_for_room(
                room_doc_name, room_number_value, capacity, allow_create,
                existing_bed_codes, stats
            )


def finalize_building_stats(building_name, stats):
    """After any room/bed write, refresh the building's setup status + derived totals. [#o7ywrx]"""
    if not (stats.created_rooms > 0 or stats.created_beds > 0 or stats.updated_rooms > 0):
        return
    total_floors = building_rollup.distinct_floor_count(building_name)
    _capacity_count = building_rollup.derive_total_capacity(building_name)
    frappe.db.set_value("Building", building_name, {
        "setup_status": "Rooms Generated",
        "setup_generated_on": today(),
        "setup_generated_by": frappe.session.user,
        "total_rooms": frappe.db.count("Room", {"building": building_name}),
        "total_floors": total_floors,
        "total_capacity": int(_capacity_count or 0),
    })


def needs_confirmation(stats) -> bool:
    """True when the plan wants to CREATE something the caller has not confirmed."""
    return (
        stats.pending_new_rooms > 0 or stats.pending_new_beds > 0
        or stats.pending_capacity_reductions > 0
    )


def generation_summary(stats) -> dict:
    """The machine-readable outcome of a run."""
    return {
        "created_rooms": stats.created_rooms,
        "updated_rooms": stats.updated_rooms,
        "skipped_rooms": stats.skipped_rooms,
        "pending_new_rooms": stats.pending_new_rooms,
        "created_beds": stats.created_beds,
        "skipped_beds": stats.skipped_beds,
        "pending_new_beds": stats.pending_new_beds,
        "failures": stats.row_failures,
        "needs_confirmation": needs_confirmation(stats),
        "pending_capacity_reductions": stats.pending_capacity_reductions,
        "retired_beds": stats.retired_beds,
        "blocked_reductions": stats.blocked_reductions,
    }


def generation_message(stats) -> str:
    """The operator-facing account of the same run."""
    if needs_confirmation(stats):
        msg = _("The floor plan adds {0} new room(s) and {1} new bed(s) that are not yet created. Existing rooms updated: {2}. Confirm to create the new rooms and beds.").format(stats.pending_new_rooms, stats.pending_new_beds, stats.updated_rooms)
        if stats.pending_capacity_reductions:
            msg += " " + _("{0} room(s) have a planned capacity reduction pending confirmation.").format(stats.pending_capacity_reductions)
    else:
        msg = _("Generation complete. Rooms created: {0}, updated: {1}, skipped (existing): {2}. Beds created: {3}.").format(stats.created_rooms, stats.updated_rooms, stats.skipped_rooms, stats.created_beds)
        if stats.retired_beds > 0:
            msg += " " + _("{0} surplus bed(s) retired (Out of Service).").format(stats.retired_beds)
    if stats.row_failures:
        failure_lines = "<br>".join(stats.row_failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(stats.row_failures)) + "<br>" + failure_lines
    if stats.blocked_reductions:
        msg += "<br><br>" + _("Capacity reductions blocked ({0} room(s) have occupied surplus beds):").format(len(stats.blocked_reductions)) + "<br>" + "<br>".join(stats.blocked_reductions)
    return msg


def generation_indicator(stats) -> str:
    """Green only when the run finished and nothing failed."""
    if needs_confirmation(stats) or stats.row_failures:
        return "orange"
    return "green"


def report_generation(stats) -> dict:
    """Emit the operator msgprint and return the summary dict. [#shn7rw]"""
    summary = generation_summary(stats)
    frappe.msgprint(
        generation_message(stats),
        title=_("Room and Bed Generation"),
        indicator=generation_indicator(stats),
    )
    return summary
