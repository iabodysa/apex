"""Custody Issue controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CustodyIssue(Document):
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one item is required on a Custody Issue."))
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))


def on_submit(doc, method=None):
    doc.db_set("status", "Issued")
    _post_custody_stock(doc)


def _post_custody_stock(doc):
    """Move stock from the building store into the employee's custody (same
    building) on the Accommodation Stock Ledger. Skipped for free-text issues
    with no linked employee."""
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if not doc.issued_to_employee or has_stock_entries("Custody Issue", doc.name):
        return
    for row in doc.items:
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.qty or 0),
                         building=doc.building, employee=None, voucher_type="Custody Issue",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.issue_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.qty or 0),
                         building=doc.building, employee=doc.issued_to_employee, voucher_type="Custody Issue",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.issue_date)


def before_cancel(doc, method=None):
    returned = frappe.get_all(
        "Custody Return",
        filters={"custody_issue": doc.name, "docstatus": 1},
        limit=1
    )
    if returned:
        frappe.throw(
            _("Cannot cancel Custody Issue {0} because it is referenced by active Custody Return {1}.").format(
                doc.name, returned[0].name
            )
        )


def on_cancel(doc, method=None):
    doc.db_set("status", "Cancelled")
    from apex_habitat.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries("Custody Issue", doc.name)

