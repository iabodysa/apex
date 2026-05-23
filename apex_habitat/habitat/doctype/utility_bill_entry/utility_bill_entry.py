"""Utility Bill Entry controller.

On submit: calculates variance from the Utility Account average, posts a
summary row to the Accommodation Ledger (ledger_type = utility_type).

Shared-meter support: when cost_bearing_pct < 100, bill_amount_sar is
computed as total_bill_amount_sar × (cost_bearing_pct / 100). The full
invoice total and the bearing percentage are preserved for audit trail.
The ledger row carries the building's actual share only.

Employee-level daily distribution is handled by the daily cost allocation
scheduled job, not here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt


class UtilityBillEntry(Document):
    def before_save(self):
        if self.doctype != "Utility Bill Entry":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if not doc.company:
        from apex_habitat.habitat.doctype.habitat_settings.habitat_settings import get_default_company
        doc.company = get_default_company()

    if doc.billing_period_to and doc.billing_period_from:
        if doc.billing_period_to < doc.billing_period_from:
            frappe.throw(_("Billing Period To must be on or after Billing Period From."))

    _compute_meter_readings(doc)
    _compute_sharing(doc)
    _compute_variance(doc)


def on_submit(doc, method=None):
    _compute_variance(doc)
    doc.db_set("variance_from_avg_pct", doc.variance_from_avg_pct)
    _post_ledger_row(doc)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))

    building = frappe.get_doc("Accommodation Building", doc.building)
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

    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": today(),
        "building": doc.building,
        "ledger_type": doc.utility_type,
        "total_site_cost": -flt(doc.bill_amount_sar),
        "capacity_denominator": building.total_capacity or 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
        "source_doctype": "Utility Bill Entry",
        "source_name": doc.name,
        "allocation_basis": "Direct",
        "reversal_of": original_row,
    }).insert(ignore_permissions=True)


def _compute_meter_readings(doc) -> None:
    prev = flt(doc.meter_reading_previous)
    curr = flt(doc.meter_reading_current)
    if curr and prev and curr >= prev:
        doc.meter_units_consumed = round(curr - prev, 3)
    elif curr and not prev:
        doc.meter_units_consumed = round(curr, 3)


def _compute_sharing(doc) -> None:
    """Compute building share from total invoice when meter is shared."""
    total = flt(doc.total_bill_amount_sar)
    pct = flt(doc.cost_bearing_pct) or 100.0

    if total > 0:
        share = total * pct / 100.0
        doc.bill_amount_sar = round(share, 2)

        if pct < 100.0:
            doc.bill_share_note = (
                f"Shared meter — {pct:.1f}% of SAR {total:,.2f} "
                f"= SAR {share:,.2f} (building share)"
            )
        else:
            doc.bill_share_note = ""


def _compute_variance(doc) -> None:
    utility_account = frappe.get_doc("Utility Account", doc.utility_account)
    avg = flt(utility_account.average_monthly_bill_sar)
    if avg > 0:
        variance = ((flt(doc.bill_amount_sar) - avg) / avg) * 100
        doc.variance_from_avg_pct = round(variance, 2)
    else:
        doc.variance_from_avg_pct = 0.0


def _post_ledger_row(doc) -> None:
    """Post one summary Accommodation Ledger row for the billing period.

    Uses bill_amount_sar (the building's actual share after bearing calculation).
    The bill_share_note provides the audit trail for shared-meter cases.
    """
    building = frappe.get_doc("Accommodation Building", doc.building)

    remarks = doc.bill_share_note or ""

    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": doc.billing_period_to,
        "building": doc.building,
        "ledger_type": doc.utility_type,
        "total_site_cost": flt(doc.bill_amount_sar),
        "capacity_denominator": building.total_capacity or 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
        "source_doctype": "Utility Bill Entry",
        "source_name": doc.name,
        "allocation_basis": "Direct",
        "allocation_period_start": doc.billing_period_from,
        "allocation_period_end": doc.billing_period_to,
        **({"remarks": remarks} if remarks else {}),
    }).insert(ignore_permissions=True)
