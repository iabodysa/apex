# Copyright (c) 2026, AFMCO and contributors
"""Accommodation Building controller.

Top-level spatial entity. Auto-sums annual cost and recomputes occupancy.
Provides bulk room/bed generation from floor plan child table.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.utils import flt, today


class Building(Document):
    pass


@frappe.whitelist()
def get_site_address(building_name, site=None, building_address=None):
    """Plain-text address shown on the building form.

    Prefers the building's own selected Address (``building_address``); else
    falls back to the Accommodation Site's address. ``site`` / ``building_address`` are
    the form's current (possibly unsaved) values so the display tracks a change before
    save; both are permission-gated, never trusted from the client. A ``None``
    arg means "not supplied" and is read from the saved record; an empty string means
    the form cleared it. Empty string when neither resolves to an Address.
    """
    frappe.has_permission("Building", "read", doc=building_name, throw=True)
    from apex.apex_core.utils.addresses import (
        get_address_text,
        get_address_text_by_name,
    )

    if building_address is None:
        building_address = frappe.db.get_value(
            "Building", building_name, "building_address"
        )
    if building_address:
        frappe.has_permission("Address", "read", doc=building_address, throw=True)
        return get_address_text_by_name(building_address)
    own = get_address_text("Building", building_name)
    if own:
        return own
    if site:
        frappe.has_permission("Site", "read", doc=site, throw=True)
    else:
        site = frappe.db.get_value("Building", building_name, "site")
    return get_address_text("Site", site)


def _room_number(abbreviation, floor_code, prefix, seq):
    """Room number ``{abbr}-{floor_code}{prefix}{seq:02d}``. A blank prefix yields the
    historical ``{abbr}-{floor_code}{seq:02d}`` byte-for-byte (no renumbering), so the
    prefix only ever ADDS a wing/block segment (e.g. ``JED1-GA01``) for non-blank rows."""
    prefix = (prefix or "").strip()
    return f"{abbreviation}-{floor_code}{prefix}{seq:02d}"


def _floor_code(floor_type, floor_num):
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


def _floor_sort_key(row):
    """Order floors bottom-to-top by classification: Basement -> Ground -> Middle -> Roof."""
    priority = {"Basement": 0, "Ground": 1, "Roof": 3}
    return (priority.get((row.floor_type or "").strip(), 2), int(row.floor_number or 0))


def _guard_abbreviation_lock(doc):
    """Once rooms exist under a building its abbreviation is LOCKED: the generator keys
    on the ``room_number`` string and never renames, so changing the code would mint a
    fresh namespace and ORPHAN every existing room. Delete the rooms first to change it."""
    if doc.is_new():
        return
    before = doc.get_doc_before_save()
    if not before or (before.abbreviation or "") == (doc.abbreviation or ""):
        return
    room_count = frappe.db.count("Room", {"building": doc.name})
    if room_count:
        frappe.throw(
            _("The building code is locked: {0} room(s) already use it in their room "
              "numbers, and renaming it would orphan them. Delete the generated rooms "
              "first if the code must change.").format(room_count),
            title=_("Building Code Locked"),
        )


_LEASE_CYCLE_FACTOR = {"Monthly": 12, "Quarterly": 4, "Semi-Annual": 2, "Annual": 1}


def apply_active_lease(doc):
    """The active Accommodation Lease is the single source of truth for rent and the
    landlord, so the building never duplicates them by hand. Derive ``annual_rent``
    from the lease (annualized by billing cycle, then the company's share) and back-fill
    ``landlord`` when it is unset. With no active lease there is no system-of-record
    rent, so the existing value is left untouched rather than zeroed."""
    lease = frappe.db.get_value(
        "Lease",
        {"building": doc.name, "status": ["in", ["Approved", "Active"]], "docstatus": ["<", 2]},
        ["rent_amount", "billing_cycle", "company_share_pct", "landlord"],
        as_dict=True,
        order_by="lease_start_date desc",
    )
    if not lease:
        return
    annual = flt(lease.rent_amount) * _LEASE_CYCLE_FACTOR.get(lease.billing_cycle, 1)
    if flt(lease.company_share_pct):
        annual = annual * flt(lease.company_share_pct) / 100.0
    doc.annual_rent = annual
    if not doc.landlord and lease.landlord:
        doc.landlord = lease.landlord


def _derive_total_capacity(building_name):
    """Count the building's real beds, excluding Out-of-Service and virtual
    ``is_temporary`` over-capacity beds. ``None`` when it has no bed rows yet (the
    pre-generation path — keep the manually-entered planned figure); 0 when it has
    beds but all are excluded.
    """
    if not frappe.db.exists("Bed", {"building": building_name}):
        return None
    return frappe.db.count(
        "Bed",
        {
            "building": building_name,
            "status": ["!=", "Out of Service"],
            "is_temporary": 0,
        },
    )


def _building_supervisor_permissions(user, building):
    return frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Building", "for_value": building},
        pluck="name",
    )


def on_update(doc, method=None):
    """Reconcile the building-scoped User Permission to the supervisor field:
    grant the new supervisor's permission for this building, drop the previous
    supervisor's; other users and other buildings are untouched."""
    before = doc.get_doc_before_save()
    old_sup = before.responsible_supervisor if before else None
    new_sup = doc.responsible_supervisor
    if old_sup == new_sup:
        return
    if old_sup:
        for perm in _building_supervisor_permissions(old_sup, doc.name):
            frappe.delete_doc("User Permission", perm, ignore_permissions=True)  # audit-ok — system permission sync
    if new_sup and not _building_supervisor_permissions(new_sup, doc.name):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": new_sup,
                "allow": "Building",
                "for_value": doc.name,
            }
        ).insert(ignore_permissions=True)  # audit-ok — system permission sync, gated by building write


_ROLLUP_TRIGGER_FIELDS = (
    "annual_rent",
    "annual_electricity",
    "annual_water",
    "annual_cleaning_staff",
    "annual_supervision",
    "annual_other_expenses",
    "total_capacity",
    "landlord",
)


def _recompute_capacity_and_cost(doc):
    """Capacity + cost-per-capacity recompute. total_capacity is read-only and
    system-derived from the live bed count, so every save must re-derive it (a bed
    going Out-of-Service is an external change the building's own field-diff can't
    see). Cheap: one count() + arithmetic — safe to run on every save."""
    apply_active_lease(doc)

    _capacity_count = _derive_total_capacity(doc.name)
    if _capacity_count is not None:
        doc.total_capacity = _capacity_count

    doc.annual_total_cost = (
        (doc.annual_rent or 0)
        + (doc.annual_electricity or 0)
        + (doc.annual_water or 0)
        + (doc.annual_cleaning_staff or 0)
        + (doc.annual_supervision or 0)
        + (doc.annual_other_expenses or 0)
    )

    if doc.total_capacity:
        doc.annual_cost_per_capacity = doc.annual_total_cost / doc.total_capacity
        doc.monthly_cost_per_capacity = doc.annual_cost_per_capacity / 12
    else:
        doc.annual_cost_per_capacity = 0
        doc.monthly_cost_per_capacity = 0


def _recompute_occupancy_and_structure(doc):
    """Occupancy / room / floor / cctv recompute — several count() queries that don't
    change unless an external writer (the assignment controller, the room/bed
    generator, weekly_occupancy_sync) touched the related rows. Guarded behind the
    trigger-field check so it doesn't run on every no-op building save."""
    doc.current_occupants = frappe.db.count(
        "Housing Assignment",
        {"building": doc.name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    if doc.total_capacity:
        doc.occupancy_percent = (doc.current_occupants / doc.total_capacity) * 100

    doc.total_rooms = frappe.db.count("Room", {"building": doc.name})
    _floor_values = frappe.db.get_all(
        "Room", filters={"building": doc.name}, pluck="floor", distinct=True
    )
    doc.total_floors = len([f for f in _floor_values if f is not None])

    doc.cctv_camera_count = frappe.db.count(
        "Facility Asset",
        {
            "building": doc.name,
            "asset_category": "CCTV Camera",
            "status": ["not in", ("Replaced", "Scrapped")],
        },
    )


_ANNUAL_COST_FIELDS = (
    "annual_rent",
    "annual_electricity",
    "annual_water",
    "annual_cleaning_staff",
    "annual_supervision",
    "annual_other_expenses",
)


def _guard_non_negative_costs(doc):
    for field in _ANNUAL_COST_FIELDS:
        if flt(doc.get(field)) < 0:
            frappe.throw(
                _("{0} cannot be negative.").format(_(doc.meta.get_label(field)))
            )


def before_save(doc, method=None):
    _guard_abbreviation_lock(doc)
    _guard_non_negative_costs(doc)
    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    _recompute_capacity_and_cost(doc)

    if doc.is_new() or any(doc.has_value_changed(f) for f in _ROLLUP_TRIGGER_FIELDS):
        _recompute_occupancy_and_structure(doc)

    if doc.floor_plan and doc.setup_status == "Draft":
        doc.setup_status = "Rooms Planned"


@frappe.whitelist(methods=["POST"])
def setup_building_rooms(building_name, floors):
    """Persist the Room Setup wizard's plan onto the building, then generate
    rooms + beds via the safe generator.

    ``floors`` is a JSON list of floor_plan rows (floor_number, floor_type,
    room_type, room_count, bed_capacity_per_room, starting_room_number,
    generate_beds). One transaction: the building's floor_plan is replaced with
    these rows, then generate_rooms_and_beds runs with confirmation granted.
    """
    rows = frappe.parse_json(floors) or []
    doc = frappe.get_doc("Building", building_name)
    doc.check_permission("write")
    doc.set("floor_plan", [])
    for r in rows:
        doc.append("floor_plan", {
            "floor_number": r.get("floor_number"),
            "floor_type": r.get("floor_type"),
            "room_type": r.get("room_type") or "Standard",
            "room_count": r.get("room_count") or 0,
            "bed_capacity_per_room": r.get("bed_capacity_per_room") or 0,
            "starting_room_number": r.get("starting_room_number") or 1,
            "generate_beds": 1 if r.get("generate_beds", 1) else 0,
        })
    doc.save()
    return generate_rooms_and_beds(
        building_name, confirm_new_rooms=1, confirm_capacity_reduction=1
    )


class _GenStats:
    """Mutable accumulator threaded through the generator's per-row helpers so the
    running counts fold in one place; the orchestrator builds the summary dict from it."""

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


def _validate_floor_plan(doc):
    """Floor-plan preconditions: at least one row, and no two floors collapsing to the
    same floor code (which would mint identical room numbers). [#caqr8g]"""
    if not doc.floor_plan:
        frappe.throw(_("No floor plan defined. Add floor rows before generating."))

    _seen_floor_codes: dict[str, int] = {}
    for _row in doc.floor_plan:
        _fc = _floor_code(_row.floor_type, int(_row.floor_number or 0))
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


def _load_existing(building_name):
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


def _apply_capacity_reductions(room_number, capacity, old_cap, existing_bed_codes, stats):
    """Retire the surplus beds when a room's planned capacity drops (confirmed path).
    Sets each unoccupied, non-temporary surplus bed Out of Service; an occupied one blocks
    the reduction. Returns True when the bed_capacity may be lowered (none blocked). [#ea5tqj]"""
    _surplus_blocked = 0
    for _b_idx in range(capacity + 1, old_cap + 1):
        _surplus_code = f"{room_number}-B{_b_idx:02d}"
        if not frappe.db.exists("Bed", _surplus_code):
            continue
        _is_temp = frappe.db.get_value("Bed", _surplus_code, "is_temporary")
        if _is_temp:
            continue
        _occupied = frappe.db.exists(
            "Housing Assignment",
            {"bed": _surplus_code, "docstatus": 1, "check_out_date": ["is", "not set"]},
        )
        if _occupied:
            _surplus_blocked += 1
        else:
            frappe.db.set_value("Bed", _surplus_code, "status", "Out of Service")
            existing_bed_codes.discard(_surplus_code)
            stats.retired_beds += 1
    if _surplus_blocked:
        stats.blocked_reductions.append(
            _("{0}: {1} occupied bed(s) prevented capacity reduction.").format(room_number, _surplus_blocked)
        )
        return False
    return True


def _reconcile_existing_room(room_doc_name, room_number, rtype, capacity,
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
        elif _apply_capacity_reductions(room_number, capacity, old_cap, existing_bed_codes, stats):
            updates["bed_capacity"] = capacity
    if updates:
        frappe.db.set_value("Room", room_doc_name, updates)
        stats.updated_rooms += 1
    else:
        stats.skipped_rooms += 1


def _create_room(building_name, room_number, floor_num, rtype, capacity, existing_room_map, stats):
    """Insert a NEW room from the plan and register it in the room map. Returns its name,
    or None when the insert failed (recorded as a row failure). [#4cp8q8]"""
    try:
        room = frappe.get_doc({
            "doctype": "Room",
            "building": building_name,
            "room_number": room_number,
            "floor": floor_num,
            "room_type": rtype,
            "bed_capacity": capacity,
            "status": "Available",
            "readiness_status": "Unknown",
        })
        room.insert(ignore_permissions=False)
        existing_room_map[room_number] = room.name
        stats.created_rooms += 1
        return room.name
    except Exception as exc:
        stats.row_failures.append(_("Room {0}: {1}").format(room_number, str(exc)))
        return None


def _generate_beds_for_room(room_doc_name, room_number, capacity, allow_create, existing_bed_codes, stats):
    """Mint the room's beds (codes ``{room}-B01..``), skipping any that already exist; when
    new beds are not yet permitted they are counted pending, not created. [#gzcnzc]"""
    for b in range(1, capacity + 1):
        bed_code = f"{room_number}-B{b:02d}"
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


def _process_floor_row(row, abbreviation, building_name, allow_create,
                       confirm_capacity_reduction, existing_room_map, existing_bed_codes, stats):
    """Generate/reconcile every room (and its beds) for one floor-plan row, in seq order."""
    floor_num = int(row.floor_number or 0)
    floor_code = _floor_code(row.floor_type, floor_num)
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
        room_number = _room_number(abbreviation, floor_code, prefix, seq)

        if room_number in existing_room_map:
            room_doc_name = existing_room_map[room_number]
            _reconcile_existing_room(
                room_doc_name, room_number, rtype, capacity,
                confirm_capacity_reduction, existing_bed_codes, stats,
            )
        elif not allow_create:
            stats.pending_new_rooms += 1
            continue
        else:
            room_doc_name = _create_room(
                building_name, room_number, floor_num, rtype, capacity, existing_room_map, stats
            )
            if room_doc_name is None:
                continue

        if gen_beds and room_doc_name:
            _generate_beds_for_room(
                room_doc_name, room_number, capacity, allow_create, existing_bed_codes, stats
            )


def _finalize_building_stats(building_name, stats):
    """After any room/bed write, refresh the building's setup status + derived totals. [#o7ywrx]"""
    if not (stats.created_rooms > 0 or stats.created_beds > 0 or stats.updated_rooms > 0):
        return
    _floor_values = frappe.db.get_all(
        "Room", filters={"building": building_name}, pluck="floor", distinct=True
    )
    _capacity_count = _derive_total_capacity(building_name)
    frappe.db.set_value("Building", building_name, {
        "setup_status": "Rooms Generated",
        "setup_generated_on": today(),
        "setup_generated_by": frappe.session.user,
        "total_rooms": frappe.db.count("Room", {"building": building_name}),
        "total_floors": len([f for f in _floor_values if f is not None]),
        "total_capacity": int(_capacity_count or 0),
    })


def _build_generation_result(stats):
    """Assemble the summary dict and emit the operator msgprint from the run's stats. [#shn7rw]"""
    needs_confirmation = (
        stats.pending_new_rooms > 0 or stats.pending_new_beds > 0 or stats.pending_capacity_reductions > 0
    )
    summary = {
        "created_rooms": stats.created_rooms,
        "updated_rooms": stats.updated_rooms,
        "skipped_rooms": stats.skipped_rooms,
        "pending_new_rooms": stats.pending_new_rooms,
        "created_beds": stats.created_beds,
        "skipped_beds": stats.skipped_beds,
        "pending_new_beds": stats.pending_new_beds,
        "failures": stats.row_failures,
        "needs_confirmation": needs_confirmation,
        "pending_capacity_reductions": stats.pending_capacity_reductions,
        "retired_beds": stats.retired_beds,
        "blocked_reductions": stats.blocked_reductions,
    }

    if needs_confirmation:
        msg = _("The floor plan adds {0} new room(s) and {1} new bed(s) that are not yet created. Existing rooms updated: {2}. Confirm to create the new rooms and beds.").format(stats.pending_new_rooms, stats.pending_new_beds, stats.updated_rooms)
        if stats.pending_capacity_reductions:
            msg += " " + _("{0} room(s) have a planned capacity reduction pending confirmation.").format(stats.pending_capacity_reductions)
        indicator = "orange"
    else:
        msg = _("Generation complete. Rooms created: {0}, updated: {1}, skipped (existing): {2}. Beds created: {3}.").format(stats.created_rooms, stats.updated_rooms, stats.skipped_rooms, stats.created_beds)
        if stats.retired_beds > 0:
            msg += " " + _("{0} surplus bed(s) retired (Out of Service).").format(stats.retired_beds)
        indicator = "green" if not stats.row_failures else "orange"
    if stats.row_failures:
        failure_lines = "<br>".join(stats.row_failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(stats.row_failures)) + "<br>" + failure_lines
    if stats.blocked_reductions:
        msg += "<br><br>" + _("Capacity reductions blocked ({0} room(s) have occupied surplus beds):").format(len(stats.blocked_reductions)) + "<br>" + "<br>".join(stats.blocked_reductions)
    frappe.msgprint(msg, title=_("Room and Bed Generation"), indicator=indicator)

    return summary


@frappe.whitelist(methods=["POST"])
def generate_rooms_and_beds(building_name, confirm_new_rooms=0, confirm_capacity_reduction=0):
    """
    Bulk generator for Accommodation Room/Bed records from the floor plan.

    Behaviour:
    - First generation (building has no rooms yet): creates everything in the plan.
    - Re-run: brings EXISTING rooms' room_type / bed_capacity in line with the plan
      (so changing a room type in the floor plan takes effect), but creating NEW
      rooms/beds (e.g. the plan's room_count was increased) requires the caller to
      pass confirm_new_rooms=1. Without it, new rooms are reported as "pending" and
      NOT created, so the building cannot silently grow from an edited floor plan.

    Returns a summary dict with created/updated/skipped/pending counts and a
    needs_confirmation flag. Never deletes existing records.
    """
    doc = frappe.get_doc("Building", building_name)
    frappe.has_permission("Building", "write", doc=doc, throw=True)

    abbreviation = (doc.abbreviation or "").strip() or doc.building_name[:4].upper().strip()

    _validate_floor_plan(doc)
    existing_room_map, existing_bed_codes = _load_existing(building_name)

    confirm_new_rooms = int(confirm_new_rooms or 0)
    confirm_capacity_reduction = int(confirm_capacity_reduction or 0)
    is_first_generation = len(existing_room_map) == 0
    allow_create = is_first_generation or bool(confirm_new_rooms)

    stats = _GenStats()
    for row in sorted(doc.floor_plan, key=_floor_sort_key):
        _process_floor_row(
            row, abbreviation, building_name, allow_create,
            confirm_capacity_reduction, existing_room_map, existing_bed_codes, stats,
        )

    _finalize_building_stats(building_name, stats)
    return _build_generation_result(stats)


_SAFETY_FREQ_MAP = {
    "Daily": "Daily",
    "Weekly": "Weekly",
    "Monthly": "Monthly",
    "Quarterly": "Quarterly",
    "Annual": "Annually",
}

_EVENT_DRIVEN_FREQUENCIES = {"As Needed", "On Entry"}


def _get_or_create_safety_template(catalog, template_freq):
    """The ONE reusable Scheduled Task Template for a Safety Task Catalog entry.

    Building-independent: a template is bound to buildings via
    Scheduled Task Assignment, never an on-template building field (that column was
    dropped). Keyed on the immutable ``safety_task_catalog`` link so re-runs and other
    buildings' setups share ONE template per catalog task. Guarantees the catalog is an
    active ``template_items`` row — the generator iterates those rows, so a template
    lacking them (e.g. one carried over from the pre-redesign model) would silently
    generate nothing. Returns ``(template_name, created)``.
    """
    existing = frappe.db.get_value(
        "Scheduled Task Template", {"safety_task_catalog": catalog.name}, "name",
        order_by="creation asc",
    )
    if existing:
        has_item = frappe.db.exists(
            "Scheduled Task Template Item",
            {"parent": existing, "parenttype": "Scheduled Task Template",
             "task_catalog": catalog.name},
        )
        if not has_item:
            tmpl = frappe.get_doc("Scheduled Task Template", existing)
            tmpl.append("template_items", {"task_catalog": catalog.name, "is_active": 1})
            tmpl.save(ignore_permissions=True)  # audit-ok — building-write gated (caller); backfills the scheduling item
        return existing, False

    title = catalog.task_title or catalog.task_code or catalog.name
    tmpl = frappe.get_doc({
        "doctype": "Scheduled Task Template",
        "template_name": f"Safety [{catalog.task_code}] {title}"[:140],
        "task_type": "Safety",
        "frequency": template_freq,
        "safety_task_catalog": catalog.name,
        "is_active": 1,
        "template_items": [{"task_catalog": catalog.name, "is_active": 1}],
    }).insert(ignore_permissions=True)  # audit-ok — building-write gated (caller); generator-only
    return tmpl.name, True


@frappe.whitelist(methods=["POST"])
def generate_safety_setup(building_name):
    """Idempotent safety-setup generator on the assignment-based model.

    For each active Safety Task Catalog entry:
      1. If not applicable_to_all_buildings, add this building to the catalog's scope
         (Safety Task Building Scope child row).
      2. Get-or-create the ONE reusable Scheduled Task Template for the catalog task
         (carrying the catalog as a template_items row), then create a Scheduled Task
         Assignment linking that template to this building. The daily generator turns
         each active assignment × item into Scheduled Task Instances.

    Frequency: catalog periods map to the template Select via ``_SAFETY_FREQ_MAP``;
    event-driven catalog tasks (``_EVENT_DRIVEN_FREQUENCIES``) have no calendar period
    and are excluded from scheduling (reported, not scheduled); any other/unknown
    frequency fails loudly rather than being silently swallowed by the closed Select.

    Idempotent: template keyed on the catalog, assignment on ``(template, building)``,
    scope on ``(catalog, building)`` — a re-run creates no duplicates. Updates the
    building's safety_setup_* stamp fields.

    Building License records are NOT created — they need a real license_number; the
    summary lists the recommended types for the operator to create manually.
    """
    frappe.has_permission("Building", "write", doc=building_name, throw=True)

    catalogs = frappe.get_all(
        "Safety Task Catalog",
        filters={"is_active": 1},
        fields=["name", "task_code", "task_title", "frequency", "applicable_to_all_buildings"],
    )

    if not catalogs:
        frappe.throw(_("No active Safety Task Catalog entries found. Run the app setup first."))

    created_scopes = 0
    skipped_scopes = 0
    created_templates = 0
    reused_templates = 0
    created_assignments = 0
    skipped_assignments = 0
    event_driven_excluded = []
    catalog_failures = []

    for catalog in catalogs:
        if not catalog.applicable_to_all_buildings:
            scope_exists = frappe.db.exists(
                "Safety Task Building Scope",
                {"parent": catalog.name, "parenttype": "Safety Task Catalog", "building": building_name},
            )
            if not scope_exists:
                try:
                    scope = frappe.new_doc("Safety Task Building Scope")
                    scope.parent = catalog.name
                    scope.parenttype = "Safety Task Catalog"
                    scope.parentfield = "applicable_buildings"
                    scope.building = building_name
                    scope.insert(ignore_permissions=True)  # audit-ok — gated by Accommodation Building write (above); generator-only cross-doctype op
                    created_scopes += 1
                except Exception as exc:
                    catalog_failures.append(
                        _("Scope for catalog {0}: {1}").format(catalog.name, str(exc))
                    )
            else:
                skipped_scopes += 1

        if catalog.frequency in _EVENT_DRIVEN_FREQUENCIES:
            event_driven_excluded.append(catalog.task_code or catalog.name)
            continue

        template_freq = _SAFETY_FREQ_MAP.get(catalog.frequency)
        if not template_freq:
            frappe.throw(
                _('Safety Task Catalog {0} has frequency "{1}", which has no scheduling '
                  "equivalent. Set a supported catalog frequency (Daily, Weekly, Monthly, "
                  "Quarterly, Annual) or map it before generating.").format(
                    catalog.name, catalog.frequency
                ),
                title=_("Unmapped Safety Frequency"),
            )

        try:
            tmpl_name, tmpl_created = _get_or_create_safety_template(catalog, template_freq)
            if tmpl_created:
                created_templates += 1
            else:
                reused_templates += 1
        except Exception as exc:
            catalog_failures.append(
                _("Template for catalog {0}: {1}").format(catalog.name, str(exc))
            )
            continue

        if frappe.db.exists(
            "Scheduled Task Assignment",
            {"template": tmpl_name, "building": building_name},
        ):
            skipped_assignments += 1
        else:
            try:
                frappe.get_doc({
                    "doctype": "Scheduled Task Assignment",
                    "template": tmpl_name,
                    "building": building_name,
                    "effective_from": today(),
                    "is_active": 1,
                }).insert(ignore_permissions=True)  # audit-ok — same building-write gate (above); generator-only
                created_assignments += 1
            except Exception as exc:
                catalog_failures.append(
                    _("Assignment for catalog {0}: {1}").format(catalog.name, str(exc))
                )

    frappe.db.set_value("Building", building_name, {
        "safety_setup_status": "Completed",
        "safety_setup_generated_on": today(),
        "safety_setup_generated_by": frappe.session.user,
    })

    summary = {
        "created_templates": created_templates,
        "reused_templates": reused_templates,
        "created_assignments": created_assignments,
        "skipped_assignments": skipped_assignments,
        "created_scopes": created_scopes,
        "skipped_scopes": skipped_scopes,
        "event_driven_excluded": event_driven_excluded,
        "failures": catalog_failures,
        "license_reminder": (
            "Building License records must be created manually with real license numbers. "
            "Recommended types: Civil Defense, Municipal Operating License, Accommodation Registration."
        ),
    }

    msg = _("Safety setup complete. Assignments created: {0}, skipped (existing): {1}. "
            "Templates created: {2}, reused: {3}.").format(
        created_assignments, skipped_assignments, created_templates, reused_templates
    )
    if event_driven_excluded:
        msg += "<br><br>" + _(
            "{0} event-driven task(s) (As Needed / On Entry) were not scheduled — they "
            "run on a trigger, not a calendar: {1}."
        ).format(len(event_driven_excluded), ", ".join(event_driven_excluded))
    if catalog_failures:
        failure_lines = "<br>".join(catalog_failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(catalog_failures)) + "<br>" + failure_lines
    frappe.msgprint(
        msg,
        title=_("Safety Setup Generator"),
        indicator="green" if not catalog_failures else "orange",
    )
    return summary


@frappe.whitelist(methods=["POST"])
def update_room_inventory(room_name, readiness_status, inventory_notes=None):
    """Allow supervisor to record room readiness without opening full form."""
    if not frappe.has_permission("Room", "write", doc=room_name):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    allowed = ("Unknown", "Ready", "Needs Cleaning", "Needs Repair", "Out of Service")
    if readiness_status not in allowed:
        frappe.throw(_("Invalid readiness status."))

    updates = {
        "readiness_status": readiness_status,
        "last_inventory_date": today(),
    }
    if inventory_notes is not None:
        updates["inventory_notes"] = inventory_notes

    frappe.db.set_value("Room", room_name, updates)
    return {"ok": True}
