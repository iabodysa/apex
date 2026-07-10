# Copyright (c) 2026, AFMCO and contributors
"""Utility Bill Entry controller.

On submit: calculates variance from the Utility Account average, posts a
summary row to the Accommodation Ledger (ledger_type = utility_type).

Shared-meter support: when cost_bearing_pct < 100, bill_amount is
computed as total_bill_amount × (cost_bearing_pct / 100). The full
invoice total and the bearing percentage are preserved for audit trail.
The ledger row carries the building's actual share only.

Employee-level daily distribution is handled by the daily cost allocation
scheduled job, not here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money


class UtilityBillEntry(Document):
    pass


def validate(doc, method=None):
    if not doc.company:
        from apex_habitat.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    if doc.billing_period_to and doc.billing_period_from:
        if doc.billing_period_to < doc.billing_period_from:
            frappe.throw(_("Billing Period To must be on or after Billing Period From."))

    # [#egssfj] overlapping (not only exact) periods for the same building+account collide
    if doc.utility_account and doc.billing_period_from and doc.billing_period_to:
        overlap = frappe.db.get_value(
            "Utility Bill Entry",
            {
                # [#p1ktdw]
                "company": doc.company,
                "building": doc.building,
                "utility_account": doc.utility_account,
                "billing_period_from": ["<=", doc.billing_period_to],
                "billing_period_to": [">=", doc.billing_period_from],
                "docstatus": ["!=", 2],
                "name": ["!=", doc.name or ""],
            },
            "name",
        )
        if overlap:
            frappe.throw(
                _("A Utility Bill Entry already overlaps this account's billing period: {0}").format(
                    overlap
                )
            )

    _compute_meter_readings(doc)
    _compute_sharing(doc)
    _compute_variance(doc)

    # reject negative amounts here; the intentional negative reversal is built
    # directly in before_cancel and never routes through validate.
    if flt(doc.total_bill_amount) < 0 or flt(doc.bill_amount) < 0:
        frappe.throw(_("Bill amounts cannot be negative."))


def on_submit(doc, method=None):
    # variance_from_avg_pct is already computed and persisted by validate() on the
    # submitting save (bill_amount is finalized there), so no recompute is needed.
    try:
        _post_ledger_row(doc)
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not post the utility cost to the ledger. The bill was not submitted."))


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))

    total_capacity = frappe.db.get_value("Building", doc.building, "total_capacity")
    from frappe.utils import today

    original_row = frappe.db.get_value(
        "Accommodation Ledger",
        {
            "source_doctype": "Utility Bill Entry",
            "source_name": doc.name,
            "reversal_of": ["is", "not set"],
        },
        "name",
    )

    try:
        frappe.get_doc({
            "doctype": "Accommodation Ledger",
            "posting_date": today(),
            "building": doc.building,
            "ledger_type": doc.utility_type,
            "total_site_cost": -flt(doc.bill_amount),
            "capacity_denominator": total_capacity or 0,
            "employee_daily_share": 0,
            "posting_mode": "Operational Memo",
            "source_doctype": "Utility Bill Entry",
            "source_name": doc.name,
            "allocation_basis": "Direct",
            "reversal_of": original_row,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback()
        frappe.throw(_("Could not post the reversal to the ledger. The cancellation was rejected."))


def _compute_meter_readings(doc) -> None:
    prev = flt(doc.meter_reading_previous)
    curr = flt(doc.meter_reading_current)
    # A meter only advances; a current below previous is a misread, not zero usage.
    if curr and prev and curr < prev:
        frappe.throw(_("Current Meter Reading cannot be lower than the Previous Meter Reading."))
    if curr and prev and curr >= prev:
        doc.meter_units_consumed = round(curr - prev, 3)
    elif curr and not prev:
        doc.meter_units_consumed = round(curr, 3)


def _compute_sharing(doc) -> None:
    """Compute building share from total invoice when meter is shared."""
    total = flt(doc.total_bill_amount)
    pct = flt(doc.cost_bearing_pct) or 100.0

    if total > 0:
        share = total * pct / 100.0
        doc.bill_amount = round(share, 2)

        if pct < 100.0:
            doc.bill_share_note = (
                f"Shared meter — {pct:.1f}% of {fmt_money(total, currency='SAR')} "
                f"= {fmt_money(share, currency='SAR')} (building share)"
            )
        else:
            doc.bill_share_note = ""


def _compute_variance(doc) -> None:
    if not doc.utility_account or not frappe.db.exists("Utility Account", doc.utility_account):
        doc.variance_from_avg_pct = 0.0
        return
    avg = flt(
        frappe.db.get_value("Utility Account", doc.utility_account, "average_monthly_bill")
    )
    if avg > 0:
        variance = ((flt(doc.bill_amount) - avg) / avg) * 100
        doc.variance_from_avg_pct = round(variance, 2)
    else:
        doc.variance_from_avg_pct = 0.0


def _post_ledger_row(doc) -> None:
    """Post one summary Accommodation Ledger row for the billing period.

    Uses bill_amount (the building's actual share after bearing calculation).
    The bill_share_note provides the audit trail for shared-meter cases.
    """
    # idempotent: skip if a live (original, not-yet-reversed) ledger row already
    # exists for this bill, so re-running the submit side-effect never double-posts.
    if _live_ledger_row(doc.name):
        return

    total_capacity = frappe.db.get_value("Building", doc.building, "total_capacity")

    remarks = doc.bill_share_note or ""

    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": doc.billing_period_to,
        "building": doc.building,
        "ledger_type": doc.utility_type,
        "total_site_cost": flt(doc.bill_amount),
        "capacity_denominator": total_capacity or 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
        "source_doctype": "Utility Bill Entry",
        "source_name": doc.name,
        "allocation_basis": "Direct",
        "allocation_period_start": doc.billing_period_from,
        "allocation_period_end": doc.billing_period_to,
        **({"remarks": remarks} if remarks else {}),
    }).insert(ignore_permissions=True)


def _live_ledger_row(source_name: str) -> str | None:
    """Name of the live ledger row for this bill, or None.

    Live = an original posting (reversal_of unset) that no later row reverses.
    """
    original = frappe.db.get_value(
        "Accommodation Ledger",
        {
            "source_doctype": "Utility Bill Entry",
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        "name",
    )
    if not original:
        return None
    if frappe.db.exists("Accommodation Ledger", {"reversal_of": original}):
        return None
    return original
