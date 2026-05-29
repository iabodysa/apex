"""Accommodation Building controller.

Top-level spatial entity. Auto-sums annual cost and recomputes occupancy.
Provides bulk room/bed generation from floor plan child table.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.utils import today


class AccommodationBuilding(Document):
    pass


def before_save(doc, method=None):
    if not doc.company:
        from apex_habitat.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

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

    doc.current_occupants = frappe.db.count(
        "Accommodation Assignment",
        {"building": doc.name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    if doc.total_capacity:
        doc.occupancy_percent = (doc.current_occupants / doc.total_capacity) * 100

    # Update setup_status when floor plan is added
    if doc.floor_plan and doc.setup_status == "Draft":
        doc.setup_status = "Rooms Planned"


@frappe.whitelist(methods=["POST"])
def generate_rooms_and_beds(building_name, confirm_new_rooms=0):
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
    if not frappe.has_permission("Accommodation Building", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
        
    doc = frappe.get_doc("Accommodation Building", building_name)
    abbreviation = (doc.abbreviation or "").strip() or doc.building_name[:4].upper().strip()

    if not doc.floor_plan:
        frappe.throw(_("No floor plan defined. Add floor rows before generating."))

    # Build existing room map: room_number → room.name
    existing_room_rows = frappe.db.get_all(
        "Accommodation Room",
        filters={"building": building_name},
        fields=["name", "room_number"],
    )
    existing_room_map = {r.room_number: r.name for r in existing_room_rows}

    # Build existing bed codes (idempotency guard)
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
    # First generation = no rooms exist yet (new rooms expected). On a re-run,
    # creating NEW rooms/beds requires explicit confirmation.
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

    for row in doc.floor_plan:
        floor_num = int(row.floor_number or 0)
        floor_code = "G" if floor_num == 0 else str(floor_num)
        start = int(row.starting_room_number or 1)
        count = int(row.room_count or 0)
        capacity = int(row.bed_capacity_per_room or 0)
        rtype = row.room_type or "Standard"
        gen_beds = int(row.generate_beds or 0)

        if count <= 0:
            continue
        # For sleeping rooms (generate_beds=1), capacity must be valid
        if gen_beds and capacity <= 0:
            frappe.throw(
                _("Beds per Room must be greater than 0 when Auto-Generate Beds is enabled. Floor {0}, type {1}.").format(floor_num, rtype)
            )
        if gen_beds and capacity > 50:
            frappe.throw(
                _("Bed capacity per room exceeds maximum of 50. Floor {0}: {1} beds configured.").format(floor_num, capacity)
            )

        for i in range(count):
            seq = start + i
            room_number = f"{abbreviation}-{floor_code}{seq:02d}"

            if room_number in existing_room_map:
                room_doc_name = existing_room_map[room_number]
                # 1b: bring an existing room's type/capacity in line with the plan
                # (changing a room type in the floor plan now takes effect on re-run).
                current = frappe.db.get_value(
                    "Accommodation Room", room_doc_name,
                    ["room_type", "bed_capacity"], as_dict=True,
                )
                updates = {}
                if current and current.room_type != rtype:
                    updates["room_type"] = rtype
                if current and (current.bed_capacity or 0) != capacity:
                    updates["bed_capacity"] = capacity
                if updates:
                    frappe.db.set_value("Accommodation Room", room_doc_name, updates)
                    updated_rooms += 1
                else:
                    skipped_rooms += 1
            else:
                # 1c: a NEW room — only create on first generation or explicit confirm.
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
                        # New bed on a re-run without confirmation — defer, don't grow silently.
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

    # Only update setup audit fields when records were created or updated.
    if created_rooms > 0 or created_beds > 0 or updated_rooms > 0:
        frappe.db.set_value("Accommodation Building", building_name, {
            "setup_status": "Rooms Generated",
            "setup_generated_on": today(),
            "setup_generated_by": frappe.session.user,
        })

    # Frappe manages the request transaction; do not commit explicitly so that
    # any unhandled error outside this block can still trigger a full rollback.

    needs_confirmation = (pending_new_rooms > 0 or pending_new_beds > 0)
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
    }

    if needs_confirmation:
        # Re-run with new rooms in the plan, but not confirmed: existing rooms were
        # updated; new ones are held back pending an explicit confirmation.
        msg = _("The floor plan adds {0} new room(s) and {1} new bed(s) that are not yet created. Existing rooms updated: {2}. Confirm to create the new rooms and beds.").format(pending_new_rooms, pending_new_beds, updated_rooms)
        indicator = "orange"
    else:
        msg = _("Generation complete. Rooms created: {0}, updated: {1}, skipped (existing): {2}. Beds created: {3}.").format(created_rooms, updated_rooms, skipped_rooms, created_beds)
        indicator = "green" if not row_failures else "orange"
    if row_failures:
        failure_lines = "<br>".join(row_failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(row_failures)) + "<br>" + failure_lines
    frappe.msgprint(msg, title=_("Room & Bed Generation"), indicator=indicator)

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
    if not frappe.has_permission("Accommodation Building", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

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
        # 1. Add building scope for tasks that are NOT global
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
                    # Permission bypass is intentional: the calling user holds write permission on
                    # Accommodation Building (checked above), but Safety Task Catalog is a
                    # master-data DocType maintained by administrators. Allowing the role to
                    # append scope rows here is an intentional cross-doctype operation that
                    # the business setup flow requires; enforcing DocType-level write on
                    # Safety Task Catalog would block legitimate supervisor-triggered setup.
                    scope.insert(ignore_permissions=True)
                    created_scopes += 1
                except Exception as exc:
                    catalog_failures.append(
                        _("Scope for catalog {0}: {1}").format(catalog.name, str(exc))
                    )
            else:
                skipped_scopes += 1

        # 2. Create Scheduled Task Template if none exists for this building+catalog
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
                # Permission bypass intentional, same rationale as above — the calling user is
                # authorized on the building, but Scheduled Task Template is owned by the
                # admin/safety-manager role. Creating templates on their behalf during
                # building setup is the intended workflow.
                }).insert(ignore_permissions=True)
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
    # Frappe manages the request transaction; do not commit explicitly so that
    # any unhandled error outside this block can still trigger a full rollback.

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
    # Per-document check: ensures the caller can write this specific room, not just
    # any Accommodation Room record at the DocType level.
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
    # Frappe manages the request transaction; do not commit explicitly.
    return {"ok": True}
