# Copyright (c) 2026, afmcoltd
"""Accommodation Checkout controller.

Vacate transaction with a custody-clearance gate. Damage deduction posting is
gated behind Habitat Settings and disabled by default.

Why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row.
It is a deliberate field overlay, not an omission: the role may read and set the
deduction fields (``cost_center``, ``damage_deduction_amount``,
``additional_salary_deduction``) on a checkout that Accommodation Manager or Resident
Supervisor opens, and may not open, create, submit or cancel it. Document access is
resolved from permlevel-0 rows only, field access is resolved separately and unions
every permlevel across the user's roles, so the two are independent grants -- the row
activates the moment one user holds both roles, with no DocPerm edit. No shipped role
profile bundles them today, so this overlay is dormant until an administrator does.
The framework's rule, written here rather than pointed at: permlevel access is the UNION
of the caller's roles (frappe/permissions.py get_role_permissions), so a user holding both
roles reads the union of both field sets and no DocPerm edit is needed to widen him.

The three writes pass ``ignore_permissions`` because they are consequences of a submit, not
actions the operator took. Submitting a checkout spawns the damage assessment, withdraws it again
if it is left orphaned, and raises the departure transport request; the permission that mattered
was checked when this document was submitted. Granting the checkout role create on Custody Damage
Assessment and Transport Request would let it raise either with no checkout behind it, and delete
on the assessment would be worse still.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex.habitat.doctype.housing_assignment.housing_assignment import recalculate_spatial
from apex.apex_core.utils.party_link import sync_party_employee

DEPARTURE_REASONS = ("Final Exit", "End of Contract")

class HousingCheckout(Document):
    def before_submit(self):
        """Blocks submission while the resident still holds custody not Returned, Lost, or Damaged."""
        before_submit(self)

def validate(doc, method=None):
    """Blocks an invalid or duplicate checkout and autofills its employee, bed, and custody rows."""
    sync_party_employee(doc, derive_from="assignment")
    if not doc.assignment or not frappe.db.exists("Housing Assignment", doc.assignment):
        return

    assignment = frappe.get_doc("Housing Assignment", doc.assignment)

    if assignment.docstatus != 1:
        frappe.throw(_("Linked Housing Assignment must be submitted."))

    if assignment.check_out_date:
        frappe.throw(_("Linked Housing Assignment already has a check-out date: {0}").format(assignment.check_out_date))

    if doc.checkout_date and assignment.check_in_date and getdate(doc.checkout_date) < getdate(assignment.check_in_date):
        frappe.throw(_("Checkout date cannot be earlier than assignment check-in date."))

    duplicate = frappe.db.get_value(
        "Housing Checkout",
        {"assignment": doc.assignment, "docstatus": 1, "name": ["!=", doc.name]},
    )
    if duplicate:
        frappe.throw(_("A submitted Housing Checkout already exists for this assignment: {0}").format(duplicate))

    if not doc.employee:
        doc.employee = assignment.employee
    if not doc.bed:
        doc.bed = assignment.bed
    if not doc.cost_center:
        doc.cost_center = assignment.cost_center

    _autofetch_outstanding_custody(doc)
    _populate_issued_quantities(doc)
    _roll_up_damage_deduction(doc)

    _VALID_TERMINAL = {"Returned", "Lost", "Damaged"}
    for row in doc.custody_return_items or []:
        if row.return_status not in _VALID_TERMINAL:
            frappe.throw(
                _("Each custody item must be marked Returned, Lost, or Damaged before submission.")
            )
    if doc.custody_return_items:
        all_returned = all(r.return_status == "Returned" for r in doc.custody_return_items)
        doc.custody_cleared = 1 if all_returned else 0

def before_submit(doc, method=None):
    """Custody-clearance gate: the checkout cannot submit while the resident still
    holds custody that has not been resolved. An article is resolved when its row
    is marked Lost/Damaged, or marked Returned with the outstanding quantity
    actually returned. validate() has already auto-fetched the outstanding set, so
    a missing row here means it was deleted after the fetch — still a block."""
    outstanding = _outstanding_custody_for_party(
        doc.party_type, doc.party, doc.employee
    )
    if not outstanding:
        return
    rows_by_article = {row.article: row for row in (doc.custody_return_items or []) if row.article}
    unresolved = []
    for article, qty in outstanding.items():
        row = rows_by_article.get(article)
        if row is None:
            unresolved.append(article)
            continue
        if row.return_status == "Returned" and (row.quantity_returned or 0) < qty:
            unresolved.append(article)
    if unresolved:
        frappe.throw(
            _("Cannot check out while the resident still holds custody. Resolve each item (return it, or mark it Lost/Damaged): {0}").format(
                ", ".join(sorted(unresolved))
            )
        )

def _issued_quantities_for_employee(employee):
    """Total quantity issued per Custody Article to an employee, summed across all
    SUBMITTED Custody Issues. Returned as {article: qty}.

    Accommodation Checkout is keyed to an Assignment/Employee (not to one Custody
    Issue), and the Accommodation Custody Return Item child carries no parent
    Custody Issue link — so the original issued quantity cannot be fetched via a
    direct link and is instead aggregated here from the issuing Custody Issues."""
    issued = {}
    if not employee:
        return issued
    rows = frappe.get_all(
        "Custody Issue Item",
        filters={
            "parenttype": "Custody Issue",
            "parent": [
                "in",
                frappe.get_all(
                    "Custody Issue",
                    filters={"issued_to_employee": employee, "docstatus": 1},
                    pluck="name",
                ),
            ],
        },
        fields=["article", "qty"],
    )
    for r in rows:
        issued[r.article] = issued.get(r.article, 0) + (r.qty or 0)
    return issued

def _issued_quantities_for_party(party_type, party, employee=None):
    """Return issued quantities for either supported resident identity."""
    if party_type == "Employee" and employee:
        return _issued_quantities_for_employee(employee)
    if not party_type or not party:
        return {}
    issues = frappe.get_all(
        "Custody Issue",
        filters={
            "party_type": party_type,
            "party": party,
            "docstatus": 1,
        },
        pluck="name",
    )
    if not issues:
        return {}
    issued = {}
    for row in frappe.get_all(
        "Custody Issue Item",
        filters={"parent": ["in", issues]},
        fields=["article", "qty"],
    ):
        issued[row.article] = issued.get(row.article, 0) + (row.qty or 0)
    return issued

def _populate_issued_quantities(doc):
    """Stamp each custody-return row's read-only quantity_issued with the total
    quantity of that article issued to the resident employee (the original
    issued quantity). Leaves rows untouched when the employee or article is
    unknown."""
    if not doc.custody_return_items:
        return
    issued = _issued_quantities_for_party(
        doc.party_type, doc.party, doc.employee
    )
    for row in doc.custody_return_items:
        if row.article:
            row.quantity_issued = issued.get(row.article, 0)

def _outstanding_custody_for_employee(employee):
    """Net quantity of each Custody Article still in the employee's hands, taken
    from the canonical Accommodation Stock Ledger balance (issue rows add, return
    rows reverse). Returns {article: qty} for positive balances only.

    This is the same definition the Accommodation Stock Balance report's employee
    custody view and the value-at-risk Number Card use; it is reused here rather
    than re-derived so the checkout cannot drift to a second, conflicting notion
    of 'outstanding'."""
    outstanding = {}
    if not employee:
        return outstanding
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "is_cancelled": 0,
            "item_type": "Custody Article",
            "employee": employee,
        },
        fields=["item", "signed_qty"],
    )
    for r in rows:
        outstanding[r.item] = outstanding.get(r.item, 0) + (r.signed_qty or 0)
    return {article: qty for article, qty in outstanding.items() if qty > 0}

def _outstanding_custody_for_party(party_type, party, employee=None):
    """Return canonical held quantities for Employee or Temporary Worker."""
    if party_type == "Employee" and employee:
        return _outstanding_custody_for_employee(employee)
    if not party_type or not party:
        return {}

    from apex.habitat.api.custody_kiosk import _open_party_custody

    outstanding = {}
    for line in _open_party_custody(party_type, party):
        article = line.get("article")
        outstanding[article] = outstanding.get(article, 0) + (line.get("qty") or 0)
    return {article: qty for article, qty in outstanding.items() if qty > 0}

def _autofetch_outstanding_custody(doc):
    """Add a custody-return row for every article the resident still holds that is
    not already listed, so the checkout starts from the full outstanding set. Rows
    already present (and any user edits to them) are preserved; this only fills
    gaps, so it is safe to re-run on every save."""
    outstanding = _outstanding_custody_for_party(
        doc.party_type, doc.party, doc.employee
    )
    if not outstanding:
        return
    listed = {row.article for row in (doc.custody_return_items or []) if row.article}
    for article, qty in outstanding.items():
        if article in listed:
            continue
        doc.append(
            "custody_return_items",
            {"article": article, "quantity_returned": 0, "return_status": "Returned"},
        )

def _roll_up_damage_deduction(doc):
    """Parent damage_deduction_amount is the server-authoritative sum of the child
    rows' deduction_amount — never hand-entered, so it always reconciles to the
    lines."""
    doc.damage_deduction_amount = sum(
        (row.deduction_amount or 0) for row in (doc.custody_return_items or [])
    )

def resolve_damage_assessment_building(assignment, bed):
    """Building for the auto-created Custody Damage Assessment.

    The submitted Accommodation Assignment is the authoritative spatial record,
    so it wins; fall back to the bed's building only when the assignment has
    none. Returns None (never "") when neither is set — an empty string would
    pass as a value yet fail the mandatory Building link, silently dropping the
    assessment inside the best-effort try/except below.
    """
    return (
        assignment.get("building")
        or frappe.db.get_value("Bed", bed, "building")
        or None
    )

def _stamp_clearance(doc, clear=False):
    """Name the person who inspected and released the resident, and unname him on cancel.

    The clearance certificate signs off as ``frappe.session.user``, not the building's
    standing supervisor, who may never have seen the room. Both fields are read-only and
    written here, and a cancelled checkout drops them so no withdrawn paper keeps a
    signatory.
    """
    doc.db_set({
        "cleared_by": None if clear else frappe.session.user,
        "cleared_on": None if clear else frappe.utils.nowdate(),
    })

def on_submit(doc, method=None):
    """Closes the assignment, frees the bed, stamps the clearance, and drafts any damage assessment."""
    already = frappe.db.get_value(
        "Housing Assignment", doc.assignment, "check_out_date", for_update=True
    )
    if already:
        frappe.throw(_("This assignment was already checked out on {0}.").format(already))

    _stamp_clearance(doc)

    assignment = frappe.get_doc("Housing Assignment", doc.assignment)
    assignment.db_set("check_out_date", doc.checkout_date)
    assignment.add_comment("Comment", _("Check-out processed via {0} on {1}").format(doc.name, doc.checkout_date))

    frappe.db.set_value("Bed", doc.bed, "status", "Available")
    frappe.db.set_value("Room", assignment.room, "readiness_status", "Needs Cleaning")
    recalculate_spatial(assignment.room, assignment.building)

    if doc.custody_return_items:
        has_damage = any(item.return_status in ("Damaged", "Lost") for item in doc.custody_return_items)

        if has_damage:
            building = resolve_damage_assessment_building(assignment, doc.bed)
            damage_doc = frappe.get_doc({
                "doctype": "Custody Damage Assessment",
                "employee": doc.employee,
                "assessment_date": doc.checkout_date,
                "building": building,
                "source_checkout": doc.name,
                "remarks": _("Auto-generated from Housing Checkout {0}. Review replacement costs and submit.").format(doc.name),
            })
            for item in doc.custody_return_items:
                if item.return_status in ("Damaged", "Lost"):
                    damage_doc.append("items", {
                        "article": item.article,
                        "damage_description": _("Reported during checkout ({0})").format(item.return_status),
                        "estimated_replacement_cost": 0,
                    })
            try:
                damage_doc.insert(ignore_permissions=True)
                doc.add_comment("Comment", _("Draft Damage Assessment created: {0}. Please review and submit.").format(damage_doc.name))
            except Exception:
                frappe.log_error(
                    title="Accommodation Checkout: draft Damage Assessment creation failed",
                    message=frappe.get_traceback(),
                )

    _post_return_stock(doc, assignment)

def _post_return_stock(doc, assignment):
    """Move the resident's custody off their name on the Accommodation Stock Ledger.

    Check-in credits the holder under voucher type "Housing Assignment"
    (``housing_assignment._post_checkin_custody``). Without the matching drain here the
    departed resident keeps a positive custody balance forever, the building store stays
    permanently short by what they returned, and ``_assert_policy_allows`` eventually
    refuses legitimate issues from that store on a shortage that does not physically
    exist. The ledger is ``in_create`` with no role holding create or write, so there is
    no manual correction path — it has to be posted here or not at all.

    Two shapes, and the difference is the store mirror: goods that came back re-enter the
    building store, goods recorded Lost or Damaged leave the holder without re-entering
    anywhere, because that stock is gone. A partially returned Lost/Damaged row does both.

    The party pair must be the one check-in credited, or the two legs never net out.
    """
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if not doc.custody_return_items or has_stock_entries("Housing Checkout", doc.name):
        return

    if not has_stock_entries("Housing Assignment", doc.assignment):
        return

    party_type = doc.get("party_type") or assignment.party_type
    party = doc.get("party") or assignment.party
    if not party:
        return

    building = assignment.building
    held = _outstanding_custody_for_party(party_type, party, doc.employee)
    for row in doc.custody_return_items:
        if not row.article:
            continue
        outstanding = held.get(row.article, 0)
        returned = min(row.quantity_returned or 0, outstanding)
        missing = max(outstanding - returned, 0) if row.return_status in ("Lost", "Damaged") else 0

        if returned:
            post_stock_entry(item_type="Custody Article", item=row.article, qty=-returned,
                             building=building, party_type=party_type, party=party,
                             voucher_type="Housing Checkout", voucher_no=doc.name,
                             voucher_detail_no=row.name, posting_date=doc.checkout_date)
            post_stock_entry(item_type="Custody Article", item=row.article, qty=returned,
                             building=building, voucher_type="Housing Checkout",
                             voucher_no=doc.name, voucher_detail_no=row.name,
                             posting_date=doc.checkout_date)
        if missing:
            post_stock_entry(item_type="Custody Article", item=row.article, qty=-missing,
                             building=building, party_type=party_type, party=party,
                             voucher_type="Housing Checkout", voucher_no=doc.name,
                             voucher_detail_no=row.name, posting_date=doc.checkout_date)

def _cancel_orphan_damage_assessment(doc):
    """Reverse the on_submit side-effect: the auto-created Custody Damage Assessment
    (linked back via source_checkout) is orphaned when the checkout is cancelled.
    Cancel a still-draft assessment so it does not linger. A submitted assessment is
    left for the manager to handle: it is an approved valuation served on the worker, and
    withdrawing it is the manager's decision to record on the assessment itself."""
    for cda in frappe.get_all(
        "Custody Damage Assessment",
        filters={"source_checkout": doc.name, "docstatus": 0},
        pluck="name",
    ):
        frappe.delete_doc("Custody Damage Assessment", cda, ignore_permissions=True)

def before_cancel(doc, method=None):
    """Blocks cancellation when no Cancellation Reason has been given, or when the
    custody this checkout returned has already moved on again."""
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        validate_reversal_allowed,
    )
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))
    validate_reversal_allowed("Housing Checkout", doc.name)

def on_cancel(doc, method=None):
    """Drops the clearance sign-off, cancels the draft damage assessment, puts the
    custody back on the resident's name, and reopens the stay."""
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    _stamp_clearance(doc, clear=True)
    _cancel_orphan_damage_assessment(doc)
    reverse_stock_entries("Housing Checkout", doc.name)

    assignment = frappe.get_doc("Housing Assignment", doc.assignment)

    later_checkout = frappe.db.get_value(
        "Housing Checkout",
        {"assignment": doc.assignment, "docstatus": 1, "name": ["!=", doc.name]},
    )
    if not later_checkout:
        assignment.db_set("check_out_date", None)
        assignment.add_comment("Comment", _("Check-out cancelled. Reason: {0}").format(doc.cancellation_reason))

        active_on_bed = frappe.db.count(
            "Housing Assignment",
            {
                "bed": doc.bed,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "name": ["!=", assignment.name],
            },
        )
        if active_on_bed == 0:
            frappe.db.set_value("Bed", doc.bed, "status", "Occupied")

        recalculate_spatial(assignment.room, assignment.building)

def _build_departure_transport(checkout, assignment):
    """Construct (not yet inserted) the departure Transport Request for a checkout.

    Modelled as Inter-City Relocation — the Salis transport type that carries a
    worker manifest and needs no project (the worker is leaving, not heading to a
    site). The Transport Request Worker child links an Employee only, so a
    Temporary-Worker checkout (no employee) cannot be manifested and is rejected
    by the caller before reaching here.
    """
    building = assignment.get("building")
    return frappe.get_doc({
        "doctype": "Transport Request",
        "service_line": "Inter-City Relocation",
        "request_type": "Inter-City Relocation",
        "accommodation_building": building,
        "requested_by": frappe.session.user,
        "source_channel": "Desk",
        "status": "New",
        "from_location": frappe.db.get_value("Building", building, "building_name") if building else None,
        "purpose": _("Departure transport for {0} ({1}). Raised from Housing Checkout {2}.").format(
            checkout.employee, checkout.checkout_reason, checkout.name
        ),
        "workers": [{"employee": checkout.employee, "pickup_point": building}],
    })

@frappe.whitelist(methods=["POST"])
def create_departure_transport(checkout):
    """Offer/raise the departure Transport Request for a Final Exit / End of
    Contract checkout, back-linking it onto the checkout. Idempotent: returns the
    already-linked request name if one was raised before."""
    doc = frappe.get_doc("Housing Checkout", checkout, for_update=True)
    doc.check_permission("write")

    if doc.docstatus != 1:
        frappe.throw(_("Departure transport can only be raised for a submitted checkout."))

    if doc.checkout_reason not in DEPARTURE_REASONS:
        frappe.throw(
            _("Departure transport applies only to a Final Exit or End of Contract checkout.")
        )

    if doc.departure_transport_request and frappe.db.exists(
        "Transport Request", doc.departure_transport_request
    ):
        return doc.departure_transport_request

    if not doc.employee:
        frappe.throw(
            _("A linked Employee is required to raise departure transport (the manifest cannot carry a Temporary Worker).")
        )

    assignment = frappe.get_doc("Housing Assignment", doc.assignment)
    request = _build_departure_transport(doc, assignment)
    request.insert(ignore_permissions=True)

    doc.db_set("departure_transport_request", request.name)
    doc.add_comment("Comment", _("Departure Transport Request raised: {0}").format(request.name))
    return request.name
