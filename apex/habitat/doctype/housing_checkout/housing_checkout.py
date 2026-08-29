# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.api.custody_kiosk import _open_party_custody
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    has_stock_entries,
    post_stock_entry,
    reverse_stock_entries,
    validate_reversal_allowed,
)
from apex.habitat.doctype.housing_assignment.housing_assignment import recalculate_spatial

DEPARTURE_REASONS = ("Final Exit", "End of Contract")

class HousingCheckout(Document):
    def before_submit(self):
        before_submit(self)

def validate(doc, method=None):
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
    if not doc.custody_return_items:
        return
    issued = _issued_quantities_for_party(
        doc.party_type, doc.party, doc.employee
    )
    for row in doc.custody_return_items:
        if row.article:
            row.quantity_issued = issued.get(row.article, 0)

def _outstanding_custody_for_employee(employee):
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
    if party_type == "Employee" and employee:
        return _outstanding_custody_for_employee(employee)
    if not party_type or not party:
        return {}

    outstanding = {}
    for line in _open_party_custody(party_type, party):
        article = line.get("article")
        outstanding[article] = outstanding.get(article, 0) + (line.get("qty") or 0)
    return {article: qty for article, qty in outstanding.items() if qty > 0}

def _autofetch_outstanding_custody(doc):
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
    doc.damage_deduction_amount = sum(
        (row.deduction_amount or 0) for row in (doc.custody_return_items or [])
    )

def resolve_damage_assessment_building(assignment, bed):
    return (
        assignment.get("building")
        or frappe.db.get_value("Bed", bed, "building")
        or None
    )

def _stamp_clearance(doc, clear=False):
    doc.db_set({
        "cleared_by": None if clear else frappe.session.user,
        "cleared_on": None if clear else frappe.utils.nowdate(),
    })

def on_submit(doc, method=None):
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
    for cda in frappe.get_all(
        "Custody Damage Assessment",
        filters={"source_checkout": doc.name, "docstatus": 0},
        pluck="name",
    ):
        frappe.delete_doc("Custody Damage Assessment", cda, ignore_permissions=True)

def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))
    validate_reversal_allowed("Housing Checkout", doc.name)

def on_cancel(doc, method=None):
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
    request.insert()

    doc.db_set("departure_transport_request", request.name)
    doc.add_comment("Comment", _("Departure Transport Request raised: {0}").format(request.name))
    return request.name
