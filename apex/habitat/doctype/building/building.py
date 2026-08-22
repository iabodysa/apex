# Copyright (c) 2026, afmcoltd
"""Accommodation Building controller.

Top-level spatial entity. Auto-sums annual cost and recomputes occupancy, and hosts
the whitelisted entry points for the room/bed and safety-setup generators. The
generators themselves live in ``habitat.utils.room_generator`` and
``habitat.utils.safety_setup``; the derived-figure arithmetic in
``habitat.utils.building_rollup``.

The two writes in ``on_update`` pass ``ignore_permissions`` because they maintain **User
Permission** — the framework's own access records — to keep a supervisor scoped to the building
they hold. Granting the Accommodation Manager role create and delete on User Permission to make
these legal would let that role widen anyone's access, including its own. This is the one write
where a DocPerm would be strictly more dangerous than the bypass.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from apex.habitat.utils import building_rollup, occupancy, room_generator, safety_setup


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
    doc.annual_rent = building_rollup.annualized_rent(
        lease.rent_amount, lease.billing_cycle, lease.company_share_pct
    )
    if not doc.landlord and lease.landlord:
        doc.landlord = lease.landlord


def _building_supervisor_permissions(user, building):
    """Returns the names of the User Permission rows granting a user access to a given building."""
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
            frappe.delete_doc("User Permission", perm, ignore_permissions=True)
    if new_sup and not _building_supervisor_permissions(new_sup, doc.name):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": new_sup,
                "allow": "Building",
                "for_value": doc.name,
            }
        ).insert(ignore_permissions=True)


def _recompute_capacity_and_cost(doc):
    """Capacity + cost-per-capacity recompute. total_capacity is read-only and
    system-derived from the live bed count, so every save must re-derive it (a bed
    going Out-of-Service is an external change the building's own field-diff can't
    see). Cheap: one count() + arithmetic — safe to run on every save."""
    apply_active_lease(doc)

    _capacity_count = building_rollup.derive_total_capacity(doc.name)
    if _capacity_count is not None:
        doc.total_capacity = _capacity_count

    doc.annual_total_cost = building_rollup.total_annual_cost(doc)
    doc.annual_cost_per_capacity, doc.monthly_cost_per_capacity = (
        building_rollup.cost_per_capacity(doc.annual_total_cost, doc.total_capacity)
    )


def _recompute_occupancy_and_structure(doc):
    """Occupancy / room / floor / cctv recompute — several count() queries that don't
    change unless an external writer (the assignment controller, the room/bed
    generator, weekly_occupancy_sync) touched the related rows. Guarded behind the
    trigger-field check so it doesn't run on every no-op building save."""
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
    """Guards the abbreviation lock, defaults company, and recomputes capacity and occupancy."""
    _guard_abbreviation_lock(doc)
    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    _recompute_capacity_and_cost(doc)

    if doc.is_new() or any(
        doc.has_value_changed(f) for f in building_rollup.ROLLUP_TRIGGER_FIELDS
    ):
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
    """Idempotent safety-setup generator on the assignment-based model.

    For each active Safety Task Catalog entry:
      1. If not applicable_to_all_buildings, add this building to the catalog's scope
         (Safety Task Building Scope child row).
      2. Get-or-create the ONE reusable Scheduled Task Template for the catalog task
         (carrying the catalog as a template_items row), then create a Scheduled Task
         Assignment linking that template to this building. The daily generator turns
         each active assignment × item into Scheduled Task Instances.

    Frequency: catalog periods map to the template Select via ``SAFETY_FREQ_MAP``;
    event-driven catalog tasks (``EVENT_DRIVEN_FREQUENCIES``) have no calendar period
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

    tally = safety_setup.SafetySetupTally()
    for catalog in catalogs:
        safety_setup.apply_catalog(catalog, building_name, tally)

    frappe.db.set_value("Building", building_name, {
        "safety_setup_status": "Completed",
        "safety_setup_generated_on": today(),
        "safety_setup_generated_by": frappe.session.user,
    })

    return safety_setup.report_setup(tally)
