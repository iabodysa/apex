# Copyright (c) 2026, afmcoltd
"""Accommodation Assignment controller.

The Assignment record IS the check-in and the active occupancy stay. It carries
both check_in_date and check_out_date; Accommodation Checkout closes it.

Housing records have no automatic payroll side effects. Employee cost recovery uses
the native HRMS Employee Advance path from its originating operational document.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
    reverse_stock_entries,
)
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

    ``frappe.utils.getdate`` (frappe/utils/data.py) normalises BOTH sides before the
    comparison, because a stored date may arrive as a string or a date and comparing
    the two shapes as text orders them wrongly without raising. The date shown to the
    supervisor goes through ``formatdate``, an alias for ``format_date``
    (frappe/utils/data.py:580), so it matches the format the rest of the desk uses.
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
    """Recounts a room's active assignments and updates its occupancy count and status accordingly.

    ``frappe.db.count`` (frappe/database/database.py:1269) counts in the database
    rather than by the length of a fetched list. ``Document.db_set``
    (frappe/model/document.py:1235) writes the result WITHOUT running validation or
    the save hooks: this is a derived figure recomputed from the rows that already
    exist, so re-validating the room here would re-run rules against a number this
    function is in the middle of correcting.
    """
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
    """Recounts a building's active occupants and updates its occupant count and occupancy
    percentage, notifying watchers of the Building doc room. This is the choke point every
    bed-occupancy transaction funnels through via ``recalculate_spatial`` — Housing Assignment
    submit/cancel, Housing Checkout submit/cancel, and Room Bed Transfer submit/cancel all land
    here — so a single ``notify=True`` on the occupant-count write is enough to tell every
    portal viewer of this building that its bed picture just changed.

    ``frappe.db.count`` (frappe/database/database.py:1269) does the counting and
    ``Document.db_set`` (frappe/model/document.py:1235) the write. ``notify=True`` is
    the reason ``db_set`` is used rather than a bare ``frappe.db.set_value``: only the
    document method publishes the realtime update, and without it a portal already
    open shows yesterday's bed picture until it is reloaded."""
    if not building_name:
        return
    building = frappe.get_doc("Building", building_name)
    active = frappe.db.count(
        "Housing Assignment",
        {"building": building_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    building.db_set("current_occupants", active, notify=True)
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
    """Occupies the bed and refreshes occupancy without creating a payroll deduction."""
    current_status = frappe.db.get_value("Bed", doc.bed, "status", for_update=True)
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
            for_update=True,
        )
        if occupying_asg:
            frappe.throw(
                _("Bed {0} was just taken by another assignment ({1}). Please select a different bed.").format(
                    doc.bed, occupying_asg
                )
            )

    frappe.db.set_value("Bed", doc.bed, "status", "Occupied")
    recalculate_spatial(doc.room, doc.building)

    _post_checkin_custody(doc)

def _post_checkin_custody(doc):
    """Post the items handed over at check-in to the stock ledger, so a resident who
    holds a mattress and a locker key shows a custody balance the checkout gate, the
    balance report and the value-at-risk card can all see. The store leg leaves the
    building's stock and the holder leg enters the resident's custody, exactly as a
    Custody Issue does. Idempotent through ``has_stock_entries``, which also means
    assignments submitted before this shipped stay as they are — history is left alone
    and the ledger starts from the next check-in."""
    if not doc.get("custody_items") or not doc.party:
        return
    if has_stock_entries("Housing Assignment", doc.name):
        return

    needed: dict[str, float] = {}
    for row in doc.custody_items:
        if row.article and (row.quantity or 0):
            needed[row.article] = needed.get(row.article, 0) + (row.quantity or 0)
    for article, qty in needed.items():
        available = get_store_balance("Custody Article", article, doc.building, for_update=True)
        if qty > available:
            frappe.throw(
                _("Cannot hand over {0} unit(s) of {1} from {2}: only {3} available in the store.").format(
                    qty, article, doc.building, available
                )
            )

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

    reverse_stock_entries("Housing Assignment", doc.name)

    recalculate_spatial(doc.room, doc.building)
