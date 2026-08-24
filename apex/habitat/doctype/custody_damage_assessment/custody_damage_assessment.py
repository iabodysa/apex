# Copyright (c) 2026, afmcoltd
"""Custody Damage Assessment controller.

Why Finance Manager holds TWO rows here. The permlevel-1 row is a field overlay: it
unlocks the money (``total_estimated_replacement_cost``) wherever the role can already
open the document, because document access resolves from permlevel-0 rows only while
field access is resolved separately and unions every permlevel across the user's roles.
The permlevel-0 ``read`` beside it is a separate grant, so a Finance Manager holding no
other role can open the record the ``Custody Damage Assessment Created`` notification
emails them. It is unscoped, so it reaches every building.

This DocType values the damage; it does not recover it. There is no payroll posting on
this path — no submit hook, no cancel reversal and no ``Additional Salary`` link — because
recovery from a worker's wage travels one shared chain, the native ``lending`` Loan raised
by ``apex.apex_core.utils.employee_loan_recovery`` and reached from Vehicle Incident's
submit. ``apex.apex_core.utils.employee_recovery`` stays only to service the Employee
Advance rows raised before that move, and raises no new one. A one-shot deduction raised
from here would be a parallel path with no receivable behind it and nothing to reverse
against.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from apex.apex_core.utils.party_link import sync_party_employee


class CustodyDamageAssessment(Document):
    pass


def validate(doc, method=None):
    """Syncs the party-employee link, requires a damaged item, totals the cost, and stamps sign-off."""
    sync_party_employee(doc)
    doc.total_estimated_replacement_cost = sum(
        flt(row.estimated_replacement_cost) for row in doc.items
    )
    _stamp_signoff(doc)
    _stamp_acknowledgement(doc)


def _stamp_signoff(doc):
    """Name who valued the damage and who approved that valuation, and unname each when
    the workflow leaves that state.

    A replacement-cost notice served on a worker that names nobody as its approver cannot be
    defended, and a rejected or revised assessment must never keep printing an approval it no
    longer holds. The assessor is taken the moment the record leaves Draft, which is the act of
    putting a valuation forward; the approver is taken at Approved, which the workflow bars the
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
