"""Non-Financial Depreciation Snapshot controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class NonFinancialDepreciationSnapshot(Document):
    @staticmethod
    def clear_old_logs(days=730):
        """Log Settings cleanup hook. A submittable, NON-financial snapshot of
        operational asset book values (no GL impact) that managers archive at a point
        in time for the Operational Depreciation Aging report. Registered in hooks
        ``default_log_clearing_doctypes`` and invoked by ``daily_maintenance``
        (run_log_clean_up). A two-year retention caps unbounded growth while keeping
        enough aging history; only SUBMITTED (docstatus=1) snapshots older than
        ``days`` are purged — drafts are preserved. The child ``Depreciation Snapshot
        Item`` rows are deleted explicitly FIRST, because ``frappe.db.delete`` does
        not cascade to a parent's children (unlike ``frappe.delete_doc``)."""
        from frappe.query_builder import Interval
        from frappe.query_builder.functions import Now

        parent = frappe.qb.DocType("Non-Financial Depreciation Snapshot")
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
        if policy and flt(policy.useful_life_years) > 0:  # [#dt9fyv]
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
