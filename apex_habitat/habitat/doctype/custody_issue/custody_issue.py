"""Custody Issue controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CustodyIssue(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from apex_habitat.habitat.doctype.custody_issue_item.custody_issue_item import CustodyIssueItem
        from frappe.types import DF

        amended_from: DF.Link | None
        building: DF.Link
        issue_date: DF.Date
        issued_to_employee: DF.Link | None
        issued_to_name: DF.Data | None
        items: DF.Table[CustodyIssueItem]
        naming_series: DF.Literal["CUST-ISS-.YYYY.-.####"]
        remarks: DF.SmallText | None
        status: DF.Literal["Draft", "Issued", "Returned", "Partially Returned", "Cancelled"]
    # end: auto-generated types
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one item is required on a Custody Issue."))
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))


def on_submit(doc, method=None):
    doc.db_set("status", "Issued")


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

