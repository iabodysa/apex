# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, today

from apex.apex_core.utils.company import display_currency, resolve_company
from apex.apex_core.utils.date_ranges import has_overlapping_record


class UtilityBillEntry(Document):
    def on_cancel(self):
        _post_reversal_row(self)


def validate(doc, method=None):
    if not doc.company:
        doc.company = resolve_company("Habitat")

    if doc.billing_period_to and doc.billing_period_from:
        if doc.billing_period_to < doc.billing_period_from:
            frappe.throw(_("Billing Period To must be on or after Billing Period From."))

    if doc.utility_account and doc.billing_period_from and doc.billing_period_to:
        overlap = has_overlapping_record(
            "Utility Bill Entry",
            {
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

    if flt(doc.total_bill_amount) < 0 or flt(doc.bill_amount) < 0:
        frappe.throw(_("Bill amounts cannot be negative."))


def on_submit(doc, method=None):
    _post_ledger_row(doc)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))


def _compute_meter_readings(doc) -> None:
    prev = flt(doc.meter_reading_previous)
    curr = flt(doc.meter_reading_current)
    if curr and prev and curr < prev:
        frappe.throw(_("Current Meter Reading cannot be lower than the Previous Meter Reading."))
    if curr and prev and curr >= prev:
        doc.meter_units_consumed = round(curr - prev, 3)
    elif curr and not prev:
        doc.meter_units_consumed = round(curr, 3)


def _compute_sharing(doc) -> None:
    total = flt(doc.total_bill_amount)
    pct = flt(doc.cost_bearing_pct) or 100.0

    if total > 0:
        share = total * pct / 100.0
        doc.bill_amount = round(share, 2)

        if pct < 100.0:
            doc.bill_share_note = _(
                "Shared meter — {0}% of {1} = {2} (building share)"
            ).format(
                f"{pct:.1f}",
                fmt_money(total, currency=display_currency()),
                fmt_money(share, currency=display_currency()),
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
