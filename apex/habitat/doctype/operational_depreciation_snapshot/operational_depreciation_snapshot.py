# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now
from frappe.utils import flt

from apex.apex_core.doctype.habitat_settings.habitat_settings import effective_retention_days


class OperationalDepreciationSnapshot(Document):
    @staticmethod
    def clear_old_logs(days=None):
        days = effective_retention_days("depreciation_snapshot_retention_days", days)
        parent = frappe.qb.DocType("Operational Depreciation Snapshot")
        cutoff = Now() - Interval(days=days)
        names = [
            row[0]
            for row in (
                frappe.qb.from_(parent)
                .select(parent.name)
                .where((parent.modified < cutoff) & (parent.docstatus == 1))
            ).run()
        ]
        if not names:
            return
        child = frappe.qb.DocType("Depreciation Snapshot Item")
        frappe.db.delete(child, filters=(child.parent.isin(names)))
        frappe.db.delete(parent, filters=(parent.name.isin(names)))


def validate(doc, method=None):
    _compute_book_values(doc)
    doc.total_book_value = sum(flt(row.book_value) for row in doc.items)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Depreciation Snapshot."))


def _compute_book_values(doc):
    policy_cache: dict[str, "Document"] = {}
    for row in doc.items:
        if row.policy and row.policy not in policy_cache:
            policy_cache[row.policy] = frappe.get_doc(
                "Operational Depreciation Policy", row.policy
            )

    for row in doc.items:
        original = flt(row.original_cost)
        age = flt(row.age_years)
        policy = policy_cache.get(row.policy) if row.policy else None
        if policy and flt(policy.useful_life_years) > 0:
            life = flt(policy.useful_life_years)
            residual_pct = flt(policy.residual_value_pct) / 100
            residual = original * residual_pct
            depreciable = original - residual
            if policy.depreciation_method == "Declining Balance":
                rate = 1 - (residual_pct ** (1 / life)) if life > 0 and residual_pct > 0 else (1 / life if life > 0 else 0)
                row.book_value = original * ((1 - rate) ** age)
            else:
                annual = depreciable / life if life > 0 else 0
                row.book_value = max(residual, original - annual * age)
        else:
            row.book_value = original
