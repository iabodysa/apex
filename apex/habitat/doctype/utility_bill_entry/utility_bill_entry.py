# Copyright (c) 2026, AFMCO and contributors
"""Utility Bill Entry controller.

On submit: calculates variance from the Utility Account average, posts a
summary row to the Accommodation Ledger (ledger_type = utility_type).

On cancel the work is split the way every other reversing voucher here splits
it: before_cancel refuses (read-only, nothing written), on_cancel posts the
offsetting mirror row.

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
from frappe.utils import flt, fmt_money, today


class UtilityBillEntry(Document):
    def on_cancel(self):
        """RESTORATION half of the cancel: post the offsetting ledger row.

        A Document method rather than a module function like the rest of this
        controller, because Frappe dispatches it from the class (run_method at
        frappe/model/document.py:1005) with no hooks.py doc_events entry to
        add — this DocType registers none for on_cancel.
        """
        _post_reversal_row(self)


def validate(doc, method=None):
    if not doc.company:
        from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    if doc.billing_period_to and doc.billing_period_from:
        if doc.billing_period_to < doc.billing_period_from:
            frappe.throw(_("Billing Period To must be on or after Billing Period From."))

    # [#luwwrt]
    if doc.utility_account and doc.billing_period_from and doc.billing_period_to:
        from apex.apex_core.utils.date_ranges import has_overlapping_record
        overlap = has_overlapping_record(
            "Utility Bill Entry",
            {
                # [#p1ktdw]
                "company": doc.company,
                "building": doc.building,
                "utility_account": doc.utility_account,
            },
            "billing_period_from",
            "billing_period_to",
            doc.billing_period_from,
            doc.billing_period_to,
            doc.name,
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

    # [#laxlx5]
    if flt(doc.total_bill_amount) < 0 or flt(doc.bill_amount) < 0:
        frappe.throw(_("Bill amounts cannot be negative."))


def on_submit(doc, method=None):
    """Post this bill's period row to the Accommodation Ledger.

    No try/except around the post, for the reason _post_reversal_row gives for
    the cancel half. frappe.db.rollback() takes no savepoint, so it discarded
    the WHOLE request transaction — every row the caller wrote before reaching
    this submit, not just the bill — and then swapped the real error for a
    generic one that named no cause. Nothing here continues past a failed post;
    it rethrew, so a savepoint would be ceremony. Letting the exception
    propagate aborts the submit, surfaces the real error, and leaves Frappe's
    own request-level rollback to unwind exactly what this request wrote.
    """
    _post_ledger_row(doc)


def before_cancel(doc, method=None):
    """REFUSAL half of the cancel — reads only, writes nothing.

    Frappe dispatches before_cancel from run_before_save_methods()
    (frappe/model/document.py:414), strictly before db_update() stamps
    docstatus 2 (:428) and before on_cancel runs from run_post_save_methods()
    (:431). Every reason to refuse a cancel belongs here, where a throw leaves
    the bill and the ledger untouched.

    The offsetting ledger row is the RESTORATION half and is posted from
    UtilityBillEntry.on_cancel. Written here it would outlive any later refusal
    in the same cancel — a second before_cancel handler, or the
    check_no_back_links_exist() that run_post_save_methods() calls right after
    on_cancel (:1186) — leaving a reversal on the books for a cancel that never
    completed. Refusing costs nothing to restore either way: the mirror is a
    memo row, so unlike a stock reversal there is no physical precondition to
    pre-check, and the missing reason is the whole refusal set.
    """
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))


def _compute_meter_readings(doc) -> None:
    prev = flt(doc.meter_reading_previous)
    curr = flt(doc.meter_reading_current)
    # [#n9guyx]
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
    # [#k2wetb]
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


def _post_reversal_row(doc) -> None:
    """Offset this bill's period posting with a negated mirror row.

    Idempotent: keyed on the LIVE original, so a bill whose posting is already
    reversed writes nothing. A bill with no live original writes nothing either
    — a mirror carrying an unset reversal_of would read as a second period
    post, and _live_ledger_row would then hand it back as the live row.

    No try/except around the insert. frappe.db.rollback() discards the whole
    request transaction, including work the caller did before the cancel, and
    then swaps the real error for a generic one. Letting the exception
    propagate out of on_cancel aborts the cancel and leaves the framework's own
    request-level rollback to unwind exactly what this request wrote.
    """
    original = _live_ledger_row(doc.name)
    if not original:
        return

    total_capacity = frappe.db.get_value("Building", doc.building, "total_capacity")

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
        "reversal_of": original,
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
