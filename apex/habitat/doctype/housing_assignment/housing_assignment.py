# Copyright (c) 2026, afmcoltd
"""Accommodation Assignment controller.

The Assignment record IS the check-in and the active occupancy stay. It carries
both check_in_date and check_out_date; Accommodation Checkout closes it.

Payroll effects are gated behind the Salary Deduction Policy and disabled by default.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from apex.apex_core.doctype.salary_deduction_policy.salary_deduction_policy import (
    get_policy,
)
from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.utils.occupancy import room_status


class HousingAssignment(Document):
    pass


def on_doctype_update():
    """Bed-occupancy performance indexes, added here — not only via the legacy
    ``add_bed_assignment_index`` patch — so a freshly installed site (which marks
    patches complete without running them) gets them too. Same index names as the
    patch, so an already-migrated site's indexes are recognised as already present
    (idempotent no-op) rather than duplicated under a new name. Plain indexes, not
    UNIQUE: MariaDB has no partial/filtered UNIQUE index, so real bed-occupancy
    uniqueness stays an application-level guard (validate() + on_submit()'s
    SELECT ... FOR UPDATE), never a DB constraint."""
    from apex.apex_core.utils.ledger_index import add_index_guarded

    add_index_guarded("Housing Assignment", ["bed"], "idx_asgn_bed")

    add_index_guarded(
        "Housing Assignment",
        ["bed", "docstatus", "check_out_date"],
        "idx_asgn_bed_active",
    )


def _flag_temporary_worker_past_expiry(doc) -> None:
    """Soft-flag housing a Temporary Worker whose passport-only window has lapsed.

    Non-blocking on purpose: a supervisor may still need to house an over-window
    worker pending Iqama issuance, so this warns rather than throws. The check-in
    date (or today) is compared against the worker's computed ``expiry_date``.
    """
    if doc.party_type != "Temporary Worker" or not doc.party:
        return
    expiry = frappe.db.get_value("Temporary Worker", doc.party, "expiry_date")
    if not expiry:
        return
    as_of = doc.check_in_date or frappe.utils.today()
    if frappe.utils.getdate(expiry) < frappe.utils.getdate(as_of):
        frappe.msgprint(
            _("Temporary Worker {0}'s stay window expired on {1}.").format(
                doc.party, frappe.utils.formatdate(expiry)
            ),
            indicator="orange",
            alert=True,
        )


def recalculate_room_occupancy(room_name: str) -> None:
    """Recounts a room's active assignments and updates its occupancy count and status accordingly."""
    if not room_name:
        return
    room = frappe.get_doc("Room", room_name)
    if room.status == "Under Maintenance":
        return
    active = frappe.db.count(
        "Housing Assignment",
        {"room": room_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    room.db_set("current_occupancy", active)
    room.db_set("status", room_status(active, room.bed_capacity))


def recalculate_building_occupancy(building_name: str) -> None:
    """Recounts a building's active occupants and updates its occupant count and occupancy percentage."""
    if not building_name:
        return
    building = frappe.get_doc("Building", building_name)
    active = frappe.db.count(
        "Housing Assignment",
        {"building": building_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    building.db_set("current_occupants", active)
    if building.total_capacity:
        building.db_set("occupancy_percent", (active / building.total_capacity) * 100)


def recalculate_spatial(room_name: str, building_name: str) -> None:
    """Refreshes both the room's and the building's occupancy figures after a bed change."""
    recalculate_room_occupancy(room_name)
    recalculate_building_occupancy(building_name)


def _snapshot_agreed_rate(doc, building):
    """Fill the agreed monthly rate from the building's cost per bed, the first time only.

    A form charged to a project has to state what the bed costs, and a later re-costing of
    the building must not silently re-price a stay the resident has already signed for. Only
    a blank rate is filled, so an operator override survives every subsequent save.
    """
    if not doc.agreed_monthly_rate:
        doc.agreed_monthly_rate = building.monthly_cost_per_capacity or 0


def validate(doc, method=None):
    """Derives the cost center and rate, and blocks duplicate occupancy, mismatches, and over-capacity."""
    sync_party_employee(doc, require_party=True)

    if not doc.building or not frappe.db.exists("Building", doc.building):
        return

    building = frappe.get_doc("Building", doc.building)

    if not doc.project:
        frappe.throw(_("Project is required."))

    if not doc.cost_center:
        doc.cost_center = building.default_cost_center
    if not doc.cost_center and building.company:
        doc.cost_center = frappe.get_cached_value("Company", building.company, "cost_center")
    if not doc.cost_center:
        frappe.throw(
            _("Cost Center is required. Please set it or configure a default Cost Center on Building {0}.").format(
                doc.building
            )
        )

    _snapshot_agreed_rate(doc, building)

    if doc.stay_type == "Temporary":
        if not doc.expected_checkout_date:
            frappe.throw(_("Expected check-out date is required for temporary stays."))
        if doc.check_in_date and doc.expected_checkout_date < doc.check_in_date:
            frappe.throw(_("Expected check-out date cannot be earlier than the check-in date."))

    if doc.employee:
        active_asg = frappe.db.get_value(
            "Housing Assignment",
            {
                "employee": doc.employee,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if active_asg:
            frappe.throw(
                _("Employee {0} already has an active Housing Assignment: {1}").format(
                    doc.employee, active_asg
                )
            )
    elif doc.party and doc.party_type:
        dup = frappe.db.get_value(
            "Housing Assignment",
            {
                "party_type": doc.party_type,
                "party": doc.party,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if dup:
            frappe.throw(
                _("{0} {1} already has an active Housing Assignment: {2}").format(
                    _(doc.party_type), doc.party, dup
                )
            )

    _flag_temporary_worker_past_expiry(doc)

    bed_room = frappe.db.get_value("Bed", doc.bed, "room")
    if bed_room != doc.room:
        frappe.throw(_("Selected Bed {0} does not belong to Room {1}").format(doc.bed, doc.room))

    room = frappe.db.get_value(
        "Room", doc.room, ["building", "readiness_status"], as_dict=True
    )
    if room.building != doc.building:
        frappe.throw(
            _("Selected Room {0} does not belong to Building {1}").format(doc.room, doc.building)
        )

    if room.readiness_status in ["Needs Repair", "Needs Cleaning", "Out of Service"]:
        frappe.throw(
            _("Room {0} is currently '{1}' and cannot be assigned to an employee.").format(
                doc.room, room.readiness_status
            )
        )

    bed_status = frappe.db.get_value("Bed", doc.bed, "status")
    if bed_status == "Out of Service":
        frappe.throw(_("Selected Bed {0} is Out of Service").format(doc.bed))
    elif bed_status == "Occupied":
        occupying_asg = frappe.db.get_value(
            "Housing Assignment",
            {
                "bed": doc.bed,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if occupying_asg:
            frappe.throw(
                _("Selected Bed {0} is already occupied by Assignment {1}").format(
                    doc.bed, occupying_asg
                )
            )

    active_count = frappe.db.count(
        "Housing Assignment",
        {
            "building": doc.building,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "name": ["!=", doc.name],
        },
    )
    capacity = building.total_capacity or 0
    if capacity:
        projected = ((active_count + 1) / capacity) * 100
        if projected > 100 and not building.over_capacity_allowed:
            frappe.throw(
                _("Building is at full capacity ({0} of {1}). Over-capacity not allowed.").format(
                    active_count, capacity
                )
            )
        if projected > (building.over_capacity_threshold_percent or 120):
            frappe.msgprint(
                _("Warning: building occupancy will reach {0:.0f}%.").format(projected),
                indicator="orange",
                alert=True,
            )


def on_submit(doc, method=None):
    """Occupies the bed, refreshes occupancy, and suspends the allowance under the Rent policy."""
    Bed = frappe.qb.DocType("Bed")
    (
        frappe.qb.from_(Bed)
        .select(Bed.status)
        .where(Bed.name == doc.bed)
        .for_update()
    ).run()
    current_status = frappe.db.get_value("Bed", doc.bed, "status")
    if current_status == "Occupied":
        occupying_asg = frappe.db.get_value(
            "Housing Assignment",
            {
                "bed": doc.bed,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", doc.name],
            },
            "name",
        )
        if occupying_asg:
            frappe.throw(
                _("Bed {0} was just taken by another assignment ({1}). Please select a different bed.").format(
                    doc.bed, occupying_asg
                )
            )

    frappe.db.set_value("Bed", doc.bed, "status", "Occupied")
    recalculate_spatial(doc.room, doc.building)

    rent_rule = get_policy().get_type_rule("Rent")
    activation = rent_rule.activation_date if rent_rule else None
    if rent_rule and (not activation or doc.check_in_date >= activation):
        doc.db_set("housing_allowance_suspended", 1)
        doc.add_comment(
            "Comment",
            "Housing Allowance suspended per Salary Deduction Policy.",
        )
    else:
        doc.db_set("housing_allowance_suspended", 0)
        doc.add_comment(
            "Comment",
            "Housing Allowance not suspended - feature disabled in Salary Deduction Policy.",
        )

    _post_checkin_custody(doc)


def _post_checkin_custody(doc):
    """Post the items handed over at check-in to the stock ledger, so a resident who
    holds a mattress and a locker key shows a custody balance the checkout gate, the
    balance report and the value-at-risk card can all see. The store leg leaves the
    building's stock and the holder leg enters the resident's custody, exactly as a
    Custody Issue does. Idempotent through ``has_stock_entries``, which also means
    assignments submitted before this shipped stay as they are — history is left alone
    and the ledger starts from the next check-in."""
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if not doc.get("custody_items") or not doc.party:
        return
    if has_stock_entries("Housing Assignment", doc.name):
        return
    for row in doc.custody_items:
        if not row.article or not (row.quantity or 0):
            continue
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.quantity or 0),
                         building=doc.building, voucher_type="Housing Assignment",
                         voucher_no=doc.name, voucher_detail_no=row.name,
                         posting_date=doc.check_in_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.quantity or 0),
                         building=doc.building, party_type=doc.party_type, party=doc.party,
                         voucher_type="Housing Assignment",
                         voucher_no=doc.name, voucher_detail_no=row.name,
                         posting_date=doc.check_in_date)


def on_cancel(doc, method=None):
    """Frees the bed if no other active assignment holds it and refreshes occupancy counts."""
    active_on_bed = frappe.db.count(
        "Housing Assignment",
        {
            "bed": doc.bed,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "name": ["!=", doc.name],
        },
    )
    if active_on_bed == 0:
        frappe.db.set_value("Bed", doc.bed, "status", "Available")

    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries("Housing Assignment", doc.name)

    recalculate_spatial(doc.room, doc.building)
