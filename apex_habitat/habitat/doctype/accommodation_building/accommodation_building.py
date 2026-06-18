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


class AccommodationBuilding(Document):
    pass


@frappe.whitelist()
def get_site_address(building_name, site=None, building_address=None):
    """Plain-text address shown on the building form.

    Prefers the building's own selected Address (``building_address``, T-144); else
    falls back to the Accommodation Site's address. ``site`` / ``building_address`` are
    the form's current (possibly unsaved) values so the display tracks a change before
    save (T-138); both are permission-gated, never trusted from the client. A ``None``
    arg means "not supplied" and is read from the saved record; an empty string means
    the form cleared it. Empty string when neither resolves to an Address.
    """
    frappe.has_permission("Accommodation Building", "read", doc=building_name, throw=True)
    from apex_habitat.apex_core.utils.addresses import (
        get_address_text,
        get_address_text_by_name,
    )

    if building_address is None:
        building_address = frappe.db.get_value(
            "Accommodation Building", building_name, "building_address"
        )
    if building_address:
        frappe.has_permission("Address", "read", doc=building_address, throw=True)
        return get_address_text_by_name(building_address)
    if site:
        frappe.has_permission("Accommodation Site", "read", doc=site, throw=True)
    else:
        site = frappe.db.get_value("Accommodation Building", building_name, "site")
    return get_address_text("Accommodation Site", site)


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
    room_count = frappe.db.count("Accommodation Room", {"building": doc.name})
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
    landlord, so the building never duplicates them by hand. Derive ``annual_rent_sar``
    from the lease (annualized by billing cycle, then the company's share) and back-fill
    ``landlord`` when it is unset. With no active lease there is no system-of-record
    rent, so the existing value is left untouched rather than zeroed."""
    lease = frappe.db.get_value(
        "Accommodation Lease",
        {"building": doc.name, "status": "Active", "docstatus": ["<", 2]},
        ["rent_amount", "billing_cycle", "company_share_pct", "supplier"],
        as_dict=True,
        order_by="lease_start_date desc",
    )
    if not lease:
        return
    annual = flt(lease.rent_amount) * _LEASE_CYCLE_FACTOR.get(lease.billing_cycle, 1)
    if flt(lease.company_share_pct):
        annual = annual * flt(lease.company_share_pct) / 100.0
    doc.annual_rent_sar = annual
    if not doc.landlord and lease.supplier:
        doc.landlord = lease.supplier


def _derive_total_capacity(building_name):
    """Count the building's real beds, excluding Out-of-Service and virtual
    ``is_temporary`` over-capacity beds. ``None`` when it has no bed rows yet (the
    pre-generation path — keep the manually-entered planned figure); 0 when it has
    beds but all are excluded. [T-140]
    """
    if not frappe.db.exists("Accommodation Bed", {"building": building_name}):
        return None
    return frappe.db.count(
        "Accommodation Bed",
        {
            "building": building_name,
            "status": ["!=", "Out of Service"],
            "is_temporary": 0,
        },
    )


# [T-254] responsible_facility_supervisor is the single source of truth for the
# building-scoped User Permission; on_update reconciles the permission to the field.
def _building_supervisor_permissions(user, building):
    return frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Accommodation Building", "for_value": building},
        pluck="name",
    )


def on_update(doc, method=None):
    """Reconcile the building-scoped User Permission to the supervisor field (T-254):
    grant the new supervisor's permission for this building, drop the previous
    supervisor's; other users and other buildings are untouched."""
    before = doc.get_doc_before_save()
    old_sup = before.responsible_facility_supervisor if before else None
    new_sup = doc.responsible_facility_supervisor
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
                "allow": "Accommodation Building",
                "for_value": doc.name,
            }
        ).insert(ignore_permissions=True)  # audit-ok — system permission sync, gated by building write


def before_save(doc, method=None):
    _guard_abbreviation_lock(doc)
    if not doc.company:
        from apex_habitat.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    apply_active_lease(doc)

    # [#c25afp]
    _capacity_count = _derive_total_capacity(doc.name)
    if _capacity_count is not None:
        doc.total_capacity = _capacity_count

    doc.annual_total_cost_sar = (
        (doc.annual_rent_sar or 0)
        + (doc.annual_electricity_sar or 0)
        + (doc.annual_water_sar or 0)
        + (doc.annual_cleaning_staff_sar or 0)
        + (doc.annual_supervision_sar or 0)
        + (doc.annual_other_expenses_sar or 0)
    )

    if doc.total_capacity:
        doc.annual_cost_per_capacity_sar = doc.annual_total_cost_sar / doc.total_capacity
        doc.monthly_cost_per_capacity_sar = doc.annual_cost_per_capacity_sar / 12
    else:
        doc.annual_cost_per_capacity_sar = 0
        doc.monthly_cost_per_capacity_sar = 0

    doc.current_occupants = frappe.db.count(
        "Accommodation Assignment",
        {"building": doc.name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    if doc.total_capacity:
        doc.occupancy_percent = (doc.current_occupants / doc.total_capacity) * 100

    # [#cowl53]
    doc.total_rooms = frappe.db.count("Accommodation Room", {"building": doc.name})
    _floor_values = frappe.db.get_all(
        "Accommodation Room", filters={"building": doc.name}, pluck="floor", distinct=True
    )
    doc.total_floors = len([f for f in _floor_values if f is not None])

    # [#c9s718]
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
    doc = frappe.get_doc("Accommodation Building", building_name)
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
    doc = frappe.get_doc("Accommodation Building", building_name)
    # [#eu1e7a]
    frappe.has_permission("Accommodation Building", "write", doc=doc, throw=True)

    abbreviation = (doc.abbreviation or "").strip() or doc.building_name[:4].upper().strip()

    if not doc.floor_plan:
        frappe.throw(_("No floor plan defined. Add floor rows before generating."))

    # [#caqr8g]
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

    # [#jcmjsz]
    existing_room_rows = frappe.db.get_all(
        "Accommodation Room",
        filters={"building": building_name},
        fields=["name", "room_number"],
    )
    existing_room_map = {r.room_number: r.name for r in existing_room_rows}

    # [#fkd615]
    Bed = DocType("Accommodation Bed")
    Room = DocType("Accommodation Room")

    _bed_rows = (
        frappe.qb.from_(Bed)
        .join(Room)
        .on(Bed.room == Room.name)
        .where(Room.building == building_name)
        .select(Bed.bed_code)
        .run(as_list=True)
    )
    existing_bed_codes = {r[0] for r in _bed_rows}

    confirm_new_rooms = int(confirm_new_rooms or 0)
    # [#4qhyuv]
    is_first_generation = len(existing_room_map) == 0
    allow_create = is_first_generation or bool(confirm_new_rooms)

    created_rooms = 0
    updated_rooms = 0
    skipped_rooms = 0
    pending_new_rooms = 0
    created_beds = 0
    skipped_beds = 0
    pending_new_beds = 0

    row_failures = []
    pending_capacity_reductions = 0
    retired_beds = 0
    blocked_reductions = []
    confirm_capacity_reduction = int(confirm_capacity_reduction or 0)

    for row in sorted(doc.floor_plan, key=_floor_sort_key):
        floor_num = int(row.floor_number or 0)
        floor_code = _floor_code(row.floor_type, floor_num)
        start = int(row.starting_room_number or 1)
        count = int(row.room_count or 0)
        capacity = int(row.bed_capacity_per_room or 0)
        rtype = row.room_type or "Standard"
        gen_beds = int(row.generate_beds or 0)

        if count <= 0:
            continue
        # [#k8dzcj]
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
                # [#h26quk]
                current = frappe.db.get_value(
                    "Accommodation Room", room_doc_name,
                    ["room_type", "bed_capacity"], as_dict=True,
                )
                updates = {}
                if current and current.room_type != rtype:
                    updates["room_type"] = rtype
                if current and (current.bed_capacity or 0) != capacity:
                    old_cap = int(current.bed_capacity or 0)
                    if capacity >= old_cap:
                        # [#trx8ab]
                        updates["bed_capacity"] = capacity
                    else:
                        # [#ea5tqj]
                        if not confirm_capacity_reduction:
                            pending_capacity_reductions += 1
                        else:
                            _surplus_blocked = 0
                            for _b_idx in range(capacity + 1, old_cap + 1):
                                _surplus_code = f"{room_number}-B{_b_idx:02d}"
                                if not frappe.db.exists("Accommodation Bed", _surplus_code):
                                    continue
                                _is_temp = frappe.db.get_value("Accommodation Bed", _surplus_code, "is_temporary")
                                if _is_temp:
                                    continue
                                _occupied = frappe.db.exists(
                                    "Accommodation Assignment",
                                    {"bed": _surplus_code, "docstatus": 1, "check_out_date": ["is", "not set"]},
                                )
                                if _occupied:
                                    _surplus_blocked += 1
                                else:
                                    frappe.db.set_value("Accommodation Bed", _surplus_code, "status", "Out of Service")
                                    existing_bed_codes.discard(_surplus_code)
                                    retired_beds += 1
                            if _surplus_blocked:
                                blocked_reductions.append(
                                    _("{0}: {1} occupied bed(s) prevented capacity reduction.").format(room_number, _surplus_blocked)
                                )
                            else:
                                updates["bed_capacity"] = capacity
                if updates:
                    frappe.db.set_value("Accommodation Room", room_doc_name, updates)
                    updated_rooms += 1
                else:
                    skipped_rooms += 1
            else:
                # [#4cp8q8]
                if not allow_create:
                    pending_new_rooms += 1
                    continue
                try:
                    room = frappe.get_doc({
                        "doctype": "Accommodation Room",
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
                    room_doc_name = room.name
                    created_rooms += 1
                except Exception as exc:
                    row_failures.append(_("Room {0}: {1}").format(room_number, str(exc)))
                    continue

            if gen_beds and room_doc_name:
                for b in range(1, capacity + 1):
                    bed_code = f"{room_number}-B{b:02d}"
                    if bed_code in existing_bed_codes:
                        skipped_beds += 1
                    elif not allow_create:
                        # [#gzcnzc]
                        pending_new_beds += 1
                    else:
                        try:
                            bed = frappe.get_doc({
                                "doctype": "Accommodation Bed",
                                "room": room_doc_name,
                                "bed_code": bed_code,
                                "status": "Available",
                                "condition": "Good",
                            })
                            bed.insert(ignore_permissions=False)
                            existing_bed_codes.add(bed_code)
                            created_beds += 1
                        except Exception as exc:
                            row_failures.append(_("Bed {0}: {1}").format(bed_code, str(exc)))

    # [#o7ywrx]
    if created_rooms > 0 or created_beds > 0 or updated_rooms > 0:
        _floor_values = frappe.db.get_all(
            "Accommodation Room", filters={"building": building_name}, pluck="floor", distinct=True
        )
        # [#bcpp7m]
        _capacity_count = _derive_total_capacity(building_name)
        frappe.db.set_value("Accommodation Building", building_name, {
            "setup_status": "Rooms Generated",
            "setup_generated_on": today(),
            "setup_generated_by": frappe.session.user,
            "total_rooms": frappe.db.count("Accommodation Room", {"building": building_name}),
            "total_floors": len([f for f in _floor_values if f is not None]),
            "total_capacity": int(_capacity_count or 0),
        })

    # [#shn7rw]

    needs_confirmation = (pending_new_rooms > 0 or pending_new_beds > 0 or pending_capacity_reductions > 0)
    summary = {
        "created_rooms": created_rooms,
        "updated_rooms": updated_rooms,
        "skipped_rooms": skipped_rooms,
        "pending_new_rooms": pending_new_rooms,
        "created_beds": created_beds,
        "skipped_beds": skipped_beds,
        "pending_new_beds": pending_new_beds,
        "failures": row_failures,
        "needs_confirmation": needs_confirmation,
        "pending_capacity_reductions": pending_capacity_reductions,
        "retired_beds": retired_beds,
        "blocked_reductions": blocked_reductions,
    }

    if needs_confirmation:
        # [#hynb42]
        msg = _("The floor plan adds {0} new room(s) and {1} new bed(s) that are not yet created. Existing rooms updated: {2}. Confirm to create the new rooms and beds.").format(pending_new_rooms, pending_new_beds, updated_rooms)
        if pending_capacity_reductions:
            msg += " " + _("{0} room(s) have a planned capacity reduction pending confirmation.").format(pending_capacity_reductions)
        indicator = "orange"
    else:
        msg = _("Generation complete. Rooms created: {0}, updated: {1}, skipped (existing): {2}. Beds created: {3}.").format(created_rooms, updated_rooms, skipped_rooms, created_beds)
        if retired_beds > 0:
            msg += " " + _("{0} surplus bed(s) retired (Out of Service).").format(retired_beds)
        indicator = "green" if not row_failures else "orange"
    if row_failures:
        failure_lines = "<br>".join(row_failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(row_failures)) + "<br>" + failure_lines
    if blocked_reductions:
        msg += "<br><br>" + _("Capacity reductions blocked ({0} room(s) have occupied surplus beds):").format(len(blocked_reductions)) + "<br>" + "<br>".join(blocked_reductions)
    frappe.msgprint(msg, title=_("Room and Bed Generation"), indicator=indicator)

    return summary


@frappe.whitelist(methods=["POST"])
def generate_safety_setup(building_name):
    """
    Idempotent safety setup generator.

    For each active Safety Task Catalog entry:
      1. If not applicable_to_all_buildings: add building to scope (Safety Task Building Scope child row).
      2. Create a Scheduled Task Template linked to this building + catalog if none exists yet.


    Updates building safety_setup_status, safety_setup_generated_on, safety_setup_generated_by.
    Returns summary dict.

    Building License records are NOT created — they require a real license_number.
    The summary lists recommended license types for the operator to create manually.
    """
    # [#5fc1fk]
    frappe.has_permission("Accommodation Building", "write", doc=building_name, throw=True)

    catalogs = frappe.get_all(
        "Safety Task Catalog",
        filters={"is_active": 1},
        fields=["name", "task_code", "task_title_en", "task_title", "frequency", "applicable_to_all_buildings"],
    )

    if not catalogs:
        frappe.throw(_("No active Safety Task Catalog entries found. Run the app setup first."))

    created_scopes = 0
    skipped_scopes = 0
    created_templates = 0
    skipped_templates = 0
    catalog_failures = []

    for catalog in catalogs:
        # [#shlhjr]
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
                    # [#mx2kmt]
                    scope.insert(ignore_permissions=True)  # audit-ok — gated by Accommodation Building write (above); generator-only cross-doctype op
                    created_scopes += 1
                except Exception as exc:
                    catalog_failures.append(
                        _("Scope for catalog {0}: {1}").format(catalog.name, str(exc))
                    )
            else:
                skipped_scopes += 1

        # [#czmvar]
        template_exists = frappe.db.exists(
            "Scheduled Task Template",
            {"building": building_name, "safety_task_catalog": catalog.name},
        )
        if not template_exists:
            _freq_map = {
                "Annual": "Annually",
                "Semi-Annual": "Every 6 Months",
                "Quarterly": "Quarterly",
                "Monthly": "Monthly",
                "Weekly": "Weekly",
                "Daily": "Daily",
                "As Needed": "As Needed",
                "On Entry": "On Entry",
            }
            template_freq = _freq_map.get(catalog.frequency, catalog.frequency)
            title = catalog.task_title_en or catalog.task_code or catalog.task_title or catalog.name
            try:
                frappe.get_doc({
                    "doctype": "Scheduled Task Template",
                    "template_name": f"{title} — {building_name}"[:140],
                    "task_type": "Safety",
                    "building": building_name,
                    "safety_task_catalog": catalog.name,
                    "frequency": template_freq,
                    "is_active": 1,
                # [#18qll3]
                }).insert(ignore_permissions=True)  # audit-ok — same building-write gate (above); generator-only
                created_templates += 1
            except Exception as exc:
                catalog_failures.append(
                    _("Template for catalog {0}: {1}").format(catalog.name, str(exc))
                )
        else:
            skipped_templates += 1

    frappe.db.set_value("Accommodation Building", building_name, {
        "safety_setup_status": "Completed",
        "safety_setup_generated_on": today(),
        "safety_setup_generated_by": frappe.session.user,
    })
    # [#shn7rw]

    summary = {
        "created_templates": created_templates,
        "skipped_templates": skipped_templates,
        "created_scopes": created_scopes,
        "skipped_scopes": skipped_scopes,
        "failures": catalog_failures,
        "license_reminder": (
            "Building License records must be created manually with real license numbers. "
            "Recommended types: Civil Defense, Municipal Operating License, Accommodation Registration."
        ),
    }

    msg = _("Safety setup complete. Templates created: {0}, skipped (existing): {1}.").format(
        created_templates, skipped_templates
    )
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
    # [#6s3c91]
    if not frappe.has_permission("Accommodation Room", "write", doc=room_name):
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

    frappe.db.set_value("Accommodation Room", room_name, updates)
    # [#4dqukg]
    return {"ok": True}
