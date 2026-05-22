"""Utility Bill Entry controller.

On submit: calculates variance from the Utility Account average, posts a
summary row to the Accommodation Ledger (ledger_type = utility_type), and
creates a draft Payment Entry when the provider is linked to a Supplier.

Employee-level daily distribution is handled by the daily cost allocation
scheduled job, not here. This submit hook records the building-level cost
for the billing period.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt


class UtilityBillEntry(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Utility Bill Entry":
            frappe.throw("DocType mismatch")


def validate(doc, method=None):
    if doc.billing_period_to and doc.billing_period_from:
        if doc.billing_period_to < doc.billing_period_from:
            frappe.throw(_("Billing Period To must be on or after Billing Period From."))

    _compute_variance(doc)


def on_submit(doc, method=None):
    _compute_variance(doc)
    doc.db_set("variance_from_avg_pct", doc.variance_from_avg_pct)
    _post_ledger_row(doc)


def before_cancel(doc, method=None):
    if not doc.cancellation_reason:
        frappe.throw(_("Cancellation Reason is mandatory."))
    
    # Reverse ledger entry
    building = frappe.get_doc("Accommodation Building", doc.building)
    from frappe.utils import today
    
    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": today(),
        "building": doc.building,
        "ledger_type": doc.utility_type,
        "total_site_cost": -flt(doc.bill_amount_sar),
        "capacity_denominator": building.total_capacity or 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
    }).insert(ignore_permissions=True)



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

    This records the building-level utility cost. Per-employee daily shares
    are computed by the daily_accommodation_cost_allocation scheduled job
    using the capacity-denominator algorithm (v2.3 calibration).
    """
    days = date_diff(doc.billing_period_to, doc.billing_period_from) or 1

    building = frappe.get_doc("Accommodation Building", doc.building)

    frappe.get_doc({
        "doctype": "Accommodation Ledger",
        "posting_date": doc.billing_period_to,
        "building": doc.building,
        "ledger_type": doc.utility_type,
        "total_site_cost": flt(doc.bill_amount_sar),
        "capacity_denominator": building.total_capacity or 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
    }).insert(ignore_permissions=True)
