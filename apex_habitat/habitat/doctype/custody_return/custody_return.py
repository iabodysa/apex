"""Custody Return controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CustodyReturn(Document):
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one item is required on a Custody Return."))
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
    _validate_return_quantities(doc)


def _validate_return_quantities(doc):
    """Reject returning more than was issued, per article, across all submitted
    returns for the linked Custody Issue (prevents over-return and duplicate
    full returns)."""
    if not doc.custody_issue or not frappe.db.exists("Custody Issue", doc.custody_issue):
        # Invalid/missing link is reported by Frappe's own link validation; don't crash here.
        return
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus != 1:
        frappe.throw(_("The linked Custody Issue {0} must be submitted before returning.").format(issue.name))

    issued = {}
    for it in issue.items:
        issued[it.article] = issued.get(it.article, 0) + (it.qty or 0)

    # Quantities already returned on OTHER submitted returns for this issue.
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

    # This document's quantities, aggregated per article.
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


def on_submit(doc, method=None):
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus == 1:
        # Check if fully returned
        issued_qty = sum([item.qty for item in issue.items])

        # Aggregate total returned qty across all submitted returns for this issue
        try:
            result = frappe.db.get_value(
                "Custody Return Item",
                filters={
                    "parenttype": "Custody Return",
                    "parent": [
                        "in",
                        frappe.get_all(
                            "Custody Return",
                            filters={"custody_issue": issue.name, "docstatus": 1},
                            pluck="name",
                        ),
                    ],
                },
                fieldname="sum(qty)",
            )
            total_returned_qty = result or 0
        except Exception:
            frappe.log_error(
                title="Custody Return on_submit: qty aggregation failed",
                message=frappe.get_traceback(),
            )
            total_returned_qty = 0

        if total_returned_qty >= issued_qty:
            issue.db_set("status", "Returned")
        elif total_returned_qty > 0:
            issue.db_set("status", "Partially Returned")

    _post_return_stock(doc)


def _post_return_stock(doc):
    """Move stock from the employee's custody back into the building store on the
    Accommodation Stock Ledger."""
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if not doc.returned_by_employee or has_stock_entries("Custody Return", doc.name):
        return
    for row in doc.items:
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.qty or 0),
                         building=doc.building, employee=doc.returned_by_employee, voucher_type="Custody Return",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.return_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.qty or 0),
                         building=doc.building, employee=None, voucher_type="Custody Return",
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


def on_cancel(doc, method=None):
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.status == "Returned":
        issue.db_set("status", "Issued")
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries("Custody Return", doc.name)

