# Copyright (c) 2026, AFMCO and contributors
"""Non-Financial Depreciation Snapshot controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class OperationalDepreciationSnapshot(Document):
    @staticmethod
    def clear_old_logs(days=None):
        """Log Settings cleanup hook. A submittable, NON-financial snapshot of
        operational asset book values (no GL impact) that managers archive at a point
        in time for the Operational Depreciation Aging report. Registered in hooks
        ``default_log_clearing_doctypes`` and invoked by ``daily_maintenance``
        (run_log_clean_up). A two-year retention caps unbounded growth while keeping
        enough aging history; only SUBMITTED (docstatus=1) snapshots older than
        ``days`` are purged — drafts are preserved. The window comes from Apex
        Settings ``depreciation_snapshot_retention_days`` (default 730) when the
        caller does not pass ``days``. The child ``Depreciation Snapshot Item`` rows
        are deleted explicitly FIRST, because ``frappe.db.delete`` does not cascade
        to a parent's children (unlike ``frappe.delete_doc``)."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        from apex.apex_core.doctype.apex_settings.apex_settings import (
            effective_retention_days,
        )

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
    if not doc.items:
        frappe.throw(_("At least one asset line is required."))
    _compute_book_values(doc)
    doc.total_book_value = sum(flt(row.book_value) for row in doc.items)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is required before cancelling a Depreciation Snapshot."))


def _compute_book_values(doc):
    # Load each distinct policy once (rows often share a policy) to avoid an N+1
    # get_doc per item; cache keyed by policy name.
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
        if policy and flt(policy.useful_life_years) > 0:  # [#dt9fyv]
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
