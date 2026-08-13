# Copyright (c) 2026, afmcoltd
"""Custody Damage Assessment controller.

Why Finance Manager holds TWO rows here. The permlevel-1 row is a field overlay: it
unlocks the money (``total_estimated_replacement_cost``) wherever the role can already
open the document, because document access resolves from permlevel-0 rows only while
field access is resolved separately and unions every permlevel across the user's roles.
The permlevel-0 ``read`` beside it is a separate grant, so a Finance Manager holding no
other role can open the record the ``Custody Damage Assessment Created`` notification
emails them. It is unscoped, so it reaches every building.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.apex_core.utils.party_link import sync_party_employee


class CustodyDamageAssessment(Document):
    pass


@frappe.whitelist()
def get_deduction_status(assessment):
    """Live status of the deduction linked to a Custody Damage Assessment.

    Read-only and computed on demand so the manager sees the current state of
    the Additional Salary rather than a stale stored copy.
    """
    frappe.has_permission("Custody Damage Assessment", "read", doc=assessment, throw=True)
    entry = frappe.db.get_value("Custody Damage Assessment", assessment, "deduction_entry")
    if not entry:
        return {"entry": None, "status": "Not Created"}

    docstatus = frappe.db.get_value("Additional Salary", entry, "docstatus")
    if docstatus == 2:
        return {"entry": entry, "status": "Cancelled"}
    if docstatus == 0:
        return {"entry": entry, "status": "Draft"}

    paid = frappe.db.exists(
        "Salary Detail",
        {"additional_salary": entry, "parenttype": "Salary Slip", "docstatus": 1},
    )
    return {"entry": entry, "status": "Paid" if paid else "Submitted"}


def validate(doc, method=None):
    """Syncs the party-employee link, requires a damaged item, totals the cost, and stamps sign-off."""
    sync_party_employee(doc)
    if not doc.items:
        frappe.throw(_("At least one damaged item is required."))
    doc.total_estimated_replacement_cost = sum(
        flt(row.estimated_replacement_cost) for row in doc.items
    )
    _stamp_signoff(doc)
    _stamp_acknowledgement(doc)


def _stamp_signoff(doc):
    """Name who valued the damage and who authorised the deduction, and unname each when
    the workflow leaves that state.

    A payroll deduction whose notice names nobody as its approver cannot be defended, and a
    rejected or revised assessment must never keep printing an approval it no longer holds.
    The assessor is taken the moment the record leaves Draft, which is the act of putting a
    valuation forward; the approver is taken at Approved, which the workflow bars the
    assessor from reaching himself.
    """
    if (doc.status or "Draft") == "Draft":
        doc.assessed_by = None
    elif not doc.assessed_by:
        doc.assessed_by = frappe.session.user

    if doc.status == "Approved":
        if not doc.approved_on:
            doc.approved_on = frappe.utils.nowdate()
            doc.approved_by = frappe.session.user
    else:
        doc.approved_on = None
        doc.approved_by = None


def _stamp_acknowledgement(doc):
    """Date the service of the notice from the worker's signature itself.

    The acknowledgement date is proof that the notice was served, so it is derived from the
    signature rather than entered beside it, and it is dropped the moment the signature is
    removed — a served-on date must not outlive the thing it evidences.
    """
    if doc.worker_signature:
        if not doc.acknowledged_on:
            doc.acknowledged_on = frappe.utils.now_datetime()
    else:
        doc.acknowledged_on = None


def on_submit(doc, method=None):
    """Record the assessment only; it does not create a parallel payroll deduction path."""
    return None


def before_cancel(doc, method=None):
    """Blocks cancellation while the linked Additional Salary deduction is still submitted."""
    if doc.deduction_entry:
        deduction_docstatus = frappe.db.get_value(
            "Additional Salary", doc.deduction_entry, "docstatus"
        )
        if deduction_docstatus == 1:
            frappe.throw(
                _("Cannot cancel Custody Damage Assessment {0} because Additional Salary Deduction Entry {1} is submitted.").format(
                    doc.name, doc.deduction_entry
                )
            )


def on_cancel(doc, method=None):
    """Undo what on_submit created: the draft deduction and the two fields it
    wrote onto the source checkout.

    before_cancel has already refused the submitted-deduction case, so anything
    reaching here holds a deduction that was never paid. A draft Additional
    Salary cannot be cancelled — docstatus 0 has no cancel — so it is deleted,
    which is also what leaves the employee with no trace of a deduction that was
    withdrawn before it ever ran."""
    if not doc.deduction_entry:
        return

    if frappe.db.get_value("Additional Salary", doc.deduction_entry, "docstatus") == 0:
        entry = doc.deduction_entry
        frappe.delete_doc("Additional Salary", entry, force=True, ignore_permissions=True)

    if doc.source_checkout:
        frappe.db.set_value(
            "Housing Checkout",
            doc.source_checkout,
            {"additional_salary_deduction": None, "damage_deduction_amount": 0},
        )

    frappe.db.set_value(
        "Custody Damage Assessment", doc.name, "deduction_entry", None
    )
