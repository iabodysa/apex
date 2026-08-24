# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from apex.apex_core.utils.party_link import sync_party_employee


class CustodyDamageAssessment(Document):
    pass


def validate(doc, method=None):
    sync_party_employee(doc)
    doc.total_estimated_replacement_cost = sum(
        flt(row.estimated_replacement_cost) for row in doc.items
    )
    _stamp_signoff(doc)
    _stamp_acknowledgement(doc)


def _stamp_signoff(doc):
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
    if doc.worker_signature:
        if not doc.acknowledged_on:
            doc.acknowledged_on = frappe.utils.now_datetime()
    else:
        doc.acknowledged_on = None
