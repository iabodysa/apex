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

