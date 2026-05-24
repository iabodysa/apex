"""Non-Financial Depreciation Snapshot controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class NonFinancialDepreciationSnapshot(Document):
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one asset line is required."))
    _compute_book_values(doc)
    doc.total_book_value_sar = sum(flt(row.book_value_sar) for row in doc.items)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Depreciation Snapshot."))


def _compute_book_values(doc):
    for row in doc.items:
        original = flt(row.original_cost_sar)
        age = flt(row.age_years)
        policy = None
        if row.policy:
            policy = frappe.get_doc("Operational Depreciation Policy", row.policy)
        if policy and policy.useful_life_years:
            life = flt(policy.useful_life_years)
            residual_pct = flt(policy.residual_value_pct) / 100
            residual = original * residual_pct
            depreciable = original - residual
            if policy.depreciation_method == "Declining Balance":
                rate = 1 - (residual_pct ** (1 / life)) if life > 0 and residual_pct > 0 else (1 / life if life > 0 else 0)
                row.book_value_sar = original * ((1 - rate) ** age)
            else:
                annual = depreciable / life if life > 0 else 0
                row.book_value_sar = max(residual, original - annual * age)
        else:
            row.book_value_sar = original
