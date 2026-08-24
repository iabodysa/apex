# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from apex.apex_core.utils.addresses import get_address_text, get_address_text_by_name
from apex.apex_core.utils.company import resolve_company
from apex.habitat.utils import building_rollup, occupancy, room_generator, safety_setup


class Building(Document):
    pass


@frappe.whitelist()
def get_site_address(building_name, site=None, building_address=None):
    frappe.has_permission("Building", "read", doc=building_name, throw=True)
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


def _guard_abbreviation_lock(doc):
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


def apply_active_lease(doc):
    lease = frappe.db.get_value(
        "Lease",
        {"building": doc.name, "status": ["in", ["Approved", "Active"]], "docstatus": ["<", 2]},
        ["rent_amount", "billing_cycle", "company_share_pct", "landlord"],
        as_dict=True,
        order_by="lease_start_date desc",
    )
    if not lease:
        return
    doc.annual_rent = building_rollup.annualized_rent(
        lease.rent_amount, lease.billing_cycle, lease.company_share_pct
    )
    if not doc.landlord and lease.landlord:
        doc.landlord = lease.landlord


def on_update(doc, method=None):
    before = doc.get_doc_before_save()
    old_sup = before.responsible_supervisor if before else None
    new_sup = doc.responsible_supervisor
    if old_sup == new_sup:
        return
    if old_sup:
        for perm in frappe.get_all(
            "User Permission",
            filters={"user": old_sup, "allow": "Building", "for_value": doc.name},
            pluck="name",
        ):
            frappe.delete_doc("User Permission", perm, ignore_permissions=True)
    if new_sup and not frappe.get_all(
        "User Permission",
        filters={"user": new_sup, "allow": "Building", "for_value": doc.name},
        pluck="name",
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": new_sup,
                "allow": "Building",
                "for_value": doc.name,
            }
        ).insert(ignore_permissions=True)


def _recompute_capacity_and_cost(doc):
    apply_active_lease(doc)

    _capacity_count = building_rollup.derive_total_capacity(doc.name)
    if _capacity_count is not None:
        doc.total_capacity = _capacity_count

    doc.annual_total_cost = building_rollup.total_annual_cost(doc)
    doc.annual_cost_per_capacity, doc.monthly_cost_per_capacity = (
        building_rollup.cost_per_capacity(doc.annual_total_cost, doc.total_capacity)
    )


def _recompute_occupancy_and_structure(doc):
    doc.current_occupants = frappe.db.count(
        "Housing Assignment",
        occupancy.active_assignment_filters(building=doc.name),
    )
    if doc.total_capacity:
        doc.occupancy_percent = (doc.current_occupants / doc.total_capacity) * 100

    doc.total_rooms = frappe.db.count("Room", {"building": doc.name})
    doc.total_floors = building_rollup.distinct_floor_count(doc.name)

    doc.cctv_camera_count = frappe.db.count(
        "Facility Asset",
        {
            "building": doc.name,
            "asset_category": "CCTV Camera",
            "status": ["not in", ("Replaced", "Scrapped")],
        },
    )


def before_save(doc, method=None):
    _guard_abbreviation_lock(doc)
    if not doc.company:
        doc.company = resolve_company("Habitat")

    _recompute_capacity_and_cost(doc)

    if doc.is_new() or any(
        doc.has_value_changed(f) for f in building_rollup.ROLLUP_TRIGGER_FIELDS
    ):
        _recompute_occupancy_and_structure(doc)

    if doc.floor_plan and doc.setup_status == "Draft":
        doc.setup_status = "Rooms Planned"


@frappe.whitelist(methods=["POST"])
def setup_building_rooms(building_name, floors):
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


@frappe.whitelist(methods=["POST"])
def generate_rooms_and_beds(building_name, confirm_new_rooms=0, confirm_capacity_reduction=0):
    doc = frappe.get_doc("Building", building_name)
    frappe.has_permission("Building", "write", doc=doc, throw=True)

    abbreviation = (doc.abbreviation or "").strip() or doc.building_name[:4].upper().strip()

    room_generator.validate_floor_plan(doc)
    existing_room_map, existing_bed_codes = room_generator.load_existing(building_name)

    confirm_new_rooms = int(confirm_new_rooms or 0)
    confirm_capacity_reduction = int(confirm_capacity_reduction or 0)
    is_first_generation = len(existing_room_map) == 0
    allow_create = is_first_generation or bool(confirm_new_rooms)

    stats = room_generator.GenerationStats()
    for row in sorted(doc.floor_plan, key=room_generator.floor_sort_key):
        room_generator.process_floor_row(
            row, abbreviation, building_name, allow_create,
            confirm_capacity_reduction, existing_room_map, existing_bed_codes, stats,
        )

    room_generator.finalize_building_stats(building_name, stats)
    return room_generator.report_generation(stats)


@frappe.whitelist(methods=["POST"])
def generate_safety_setup(building_name):
    frappe.has_permission("Building", "write", doc=building_name, throw=True)

    catalogs = frappe.get_all(
        "Safety Task Catalog",
        filters={"is_active": 1},
        fields=["name", "task_code", "task_title", "frequency", "applicable_to_all_buildings"],
    )

    if not catalogs:
        frappe.throw(_("No active Safety Task Catalog entries found. Run the app setup first."))

    tally = safety_setup.SafetySetupTally()
    for catalog in catalogs:
        safety_setup.apply_catalog(catalog, building_name, tally)

    frappe.db.set_value("Building", building_name, {
        "safety_setup_status": "Completed",
        "safety_setup_generated_on": today(),
        "safety_setup_generated_by": frappe.session.user,
    })

    return safety_setup.report_setup(tally)
