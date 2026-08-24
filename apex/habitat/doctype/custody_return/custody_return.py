# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import nowdate

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    has_stock_entries,
    post_stock_entry,
    reverse_stock_entries,
    validate_reversal_allowed,
)
from apex.habitat.doctype.custody_issue.custody_issue import validate_serialized_rows


class CustodyReturn(Document):
    pass


def validate(doc, method=None):
    sync_party_employee(doc, employee_field="returned_by_employee")
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
    validate_serialized_rows(doc)
    _link_issue_lines(doc)
    _validate_return_quantities(doc)


def _link_issue_lines(doc):
    issue_rows = frappe.get_all(
        "Custody Issue Item",
        filters={"parent": doc.custody_issue, "parenttype": "Custody Issue"},
        fields=["name", "article", "serial_no"],
    ) if doc.custody_issue else []

    by_serial = {
        (row.article, (row.serial_no or "").strip()): row.name
        for row in issue_rows
        if (row.serial_no or "").strip()
    }
    by_article = {}
    for row in issue_rows:
        by_article.setdefault(row.article, []).append(row.name)

    for row in doc.items:
        serial = (row.serial_no or "").strip()
        match = by_serial.get((row.article, serial)) if serial else None
        if not match:
            candidates = by_article.get(row.article) or []
            match = candidates[0] if len(candidates) == 1 else None
        row.custody_issue_item = match


def _validate_return_quantities(doc):
    if not doc.custody_issue or not frappe.db.exists("Custody Issue", doc.custody_issue):
        return
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus != 1:
        frappe.throw(_("The linked Custody Issue {0} must be submitted before returning.").format(issue.name))

    issued = {}
    for it in issue.items:
        issued[it.article] = issued.get(it.article, 0) + (it.qty or 0)

    prior_returns = frappe.get_all(
        "Custody Return",
        filters={"custody_issue": issue.name, "docstatus": 1, "name": ["!=", doc.name or ""]},
        pluck="name",
    )
    prior = {}
    if prior_returns:
        for r in frappe.get_all(
            "Custody Return Item",
            filters={"parent": ["in", prior_returns]},
            fields=["article", "qty"],
        ):
            prior[r.article] = prior.get(r.article, 0) + (r.qty or 0)

    this_doc = {}
    for row in doc.items:
        this_doc[row.article] = this_doc.get(row.article, 0) + (row.qty or 0)

    for article, qty in this_doc.items():
        issued_qty = issued.get(article, 0)
        if issued_qty == 0:
            frappe.throw(
                _("Article {0} was not issued on Custody Issue {1}, so it cannot be returned.").format(
                    article, issue.name
                )
            )
        already = prior.get(article, 0)
        if already + qty > issued_qty:
            frappe.throw(
                _("Cannot return {0} unit(s) of {1}: {2} were issued and {3} already returned.").format(
                    qty, article, issued_qty, already
                )
            )


def _progress_from(issued, returned):
    fully = bool(issued) and all(returned.get(a, 0) >= q for a, q in issued.items())
    any_returned = any(returned.get(a, 0) > 0 for a in issued)
    return "Returned" if fully else "Partially Returned" if any_returned else "Issued"


def _issue_return_progress(issue, exclude=None):
    issued = {}
    for it in issue.items:
        issued[it.article] = issued.get(it.article, 0) + (it.qty or 0)
    submitted = [
        n for n in frappe.get_all(
            "Custody Return",
            filters={"custody_issue": issue.name, "docstatus": 1},
            pluck="name",
        ) if n != exclude
    ]
    returned = {}
    if submitted:
        for r in frappe.get_all(
            "Custody Return Item",
            filters={"parent": ["in", submitted]},
            fields=["article", "qty"],
        ):
            returned[r.article] = returned.get(r.article, 0) + (r.qty or 0)
    return _progress_from(issued, returned)


def on_submit(doc, method=None):
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus == 1:
        try:
            status = _issue_return_progress(issue)
        except Exception:
            frappe.log_error(
                title="Custody Return on_submit: return-progress computation failed",
                message=frappe.get_traceback(),
            )
            status = None
        if status and issue.status != status:
            issue.db_set("status", status)

    _post_return_stock(doc)


def _post_return_stock(doc):
    if doc.get("returned_by_employee"):
        party_type, party = "Employee", doc.returned_by_employee
    else:
        party_type, party = doc.get("party_type"), doc.get("party")
    if not party or has_stock_entries("Custody Return", doc.name):
        return
    for row in doc.items:
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.qty or 0),
                         building=doc.building, party_type=party_type, party=party,
                         voucher_type="Custody Return",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.return_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.qty or 0),
                         building=doc.building, voucher_type="Custody Return",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.return_date)


def before_cancel(doc, method=None):
    damage = frappe.get_all(
        "Custody Damage Assessment",
        filters={"custody_return": doc.name, "docstatus": 1},
        limit=1
    )
    if damage:
        frappe.throw(
            _("Cannot cancel Custody Return {0} because it is referenced by active Custody Damage Assessment {1}.").format(
                doc.name, damage[0].name
            )
        )
    validate_reversal_allowed("Custody Return", doc.name)


def on_cancel(doc, method=None):
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    try:
        status = _issue_return_progress(issue, exclude=doc.name)
        if issue.status != status:
            issue.db_set("status", status)
    except Exception:
        frappe.log_error(
            title="Custody Return on_cancel: return-progress recompute failed",
            message=frappe.get_traceback(),
        )
    reverse_stock_entries("Custody Return", doc.name)


_DAMAGED_CONDITIONS = ("Damaged", "Lost")


@frappe.whitelist()
def make_damage_assessment(source_name, target_doc=None):
    frappe.has_permission("Custody Return", "read", doc=source_name, throw=True)

    def set_missing_values(source, target):
        target.custody_return = source.name
        target.assessment_date = nowdate()

    return get_mapped_doc(
        "Custody Return",
        source_name,
        {
            "Custody Return": {
                "doctype": "Custody Damage Assessment",
                "field_map": {
                    "party_type": "party_type",
                    "party": "party",
                    "building": "building",
                },
            },
            "Custody Return Item": {
                "doctype": "Custody Damage Item",
                "field_map": {
                    "article": "article",
                    "serial_no": "serial_no",
                    "damage_note": "damage_description",
                },
                "condition": lambda row: row.condition_on_return in _DAMAGED_CONDITIONS,
            },
        },
        target_doc,
        set_missing_values,
    )
