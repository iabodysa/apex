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
    def before_save(self):
        if self.doctype != "Accommodation Building":
            frappe.throw("DocType mismatch")


def before_save(doc, method=None):
    if not doc.company:
        from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
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
def generate_rooms_and_beds(building_name):
    """
    Idempotent bulk generator: creates missing Accommodation Room and
    Accommodation Bed records from the floor plan child table.

    Returns a summary dict: {created_rooms, skipped_rooms, created_beds, skipped_beds}.
    Never deletes or overwrites existing records.
    Blocks generation if any planned room would overwrite an occupied room.
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

    created_rooms = 0
    skipped_rooms = 0
    created_beds = 0
    skipped_beds = 0

    for row in doc.floor_plan:
        floor_num = int(row.floor_number or 0)
        floor_code = "G" if floor_num == 0 else str(floor_num)
        start = int(row.starting_room_number or 1)
        count = int(row.room_count or 0)
        capacity = int(row.bed_capacity_per_room or 0)
        rtype = row.room_type or "Standard"
        gen_beds = int(row.generate_beds or 0)

        if count <= 0 or capacity <= 0:
            continue
        if capacity > 50:
            frappe.throw(_("Bed capacity per room exceeds maximum of 50. Floor {0}: {1} beds configured.").format(floor_num, capacity))

        for i in range(count):
            seq = start + i
            room_number = f"{abbreviation}-{floor_code}{seq:02d}"

            if room_number in existing_room_map:
                skipped_rooms += 1
                room_doc_name = existing_room_map[room_number]
            else:
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

            if gen_beds and room_doc_name:
                for b in range(1, capacity + 1):
                    bed_code = f"{room_number}-B{b:02d}"
                    if bed_code in existing_bed_codes:
                        skipped_beds += 1
                    else:
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

    # Only update setup audit fields when new records were created
    if created_rooms > 0 or created_beds > 0:
        frappe.db.set_value("Accommodation Building", building_name, {
            "setup_status": "Rooms Generated",
            "setup_generated_on": today(),
            "setup_generated_by": frappe.session.user,
        })

    frappe.db.commit()

    summary = {
        "created_rooms": created_rooms,
        "skipped_rooms": skipped_rooms,
        "created_beds": created_beds,
        "skipped_beds": skipped_beds,
    }

    msg = _(
        "Generation complete. Rooms created: {0}, skipped (existing): {1}. "
        "Beds created: {2}."
    ).format(created_rooms, skipped_rooms, created_beds)
    frappe.msgprint(msg, title=_("Room & Bed Generation"), indicator="green")

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

    doc = frappe.get_doc("Accommodation Building", building_name)

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

    for catalog in catalogs:
        # 1. Add building scope for tasks that are NOT global
        if not catalog.applicable_to_all_buildings:
            scope_exists = frappe.db.exists(
                "Safety Task Building Scope",
                {"parent": catalog.name, "parenttype": "Safety Task Catalog", "building": building_name},
            )
            if not scope_exists:
                scope = frappe.new_doc("Safety Task Building Scope")
                scope.parent = catalog.name
                scope.parenttype = "Safety Task Catalog"
                scope.parentfield = "applicable_buildings"
                scope.building = building_name
                scope.insert(ignore_permissions=True)
                created_scopes += 1
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
            frappe.get_doc({
                "doctype": "Scheduled Task Template",
                "template_name": f"{title} — {building_name}"[:140],
                "task_type": "Safety",
                "building": building_name,
                "safety_task_catalog": catalog.name,
                "frequency": template_freq,
                "is_active": 1,
            }).insert(ignore_permissions=True)
            created_templates += 1
        else:
            skipped_templates += 1

    frappe.db.set_value("Accommodation Building", building_name, {
        "safety_setup_status": "Completed",
        "safety_setup_generated_on": today(),
        "safety_setup_generated_by": frappe.session.user,
    })
    frappe.db.commit()

    summary = {
        "created_templates": created_templates,
        "skipped_templates": skipped_templates,
        "created_scopes": created_scopes,
        "skipped_scopes": skipped_scopes,
        "license_reminder": (
            "Building License records must be created manually with real license numbers. "
            "Recommended types: Civil Defense, Municipal Operating License, Accommodation Registration."
        ),
    }

    frappe.msgprint(
        _("Safety setup complete. Templates created: {0}, skipped (existing): {1}.").format(
            created_templates, skipped_templates
        ),
        title=_("Safety Setup Generator"),
        indicator="green",
    )
    return summary


@frappe.whitelist(methods=["POST"])
def update_room_inventory(room_name, readiness_status, inventory_notes=None):
    """Allow supervisor to record room readiness without opening full form."""
    if not frappe.has_permission("Accommodation Room", "write"):
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
    frappe.db.commit()
    return {"ok": True}
