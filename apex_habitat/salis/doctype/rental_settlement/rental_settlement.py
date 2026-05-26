"""Rental Settlement controller.

Monthly reconciliation of a Rental Office's claim against accrued rental days.
``validate`` recomputes ``accrued_total`` from the vehicle lines (and the line
amounts themselves) and the ``variance`` against the claimed total. On submit,
``create_payment_request`` may raise a finance-exclusive Salis Payment Request
(expense_type "Rental") referencing this settlement.

This controller posts NO General Ledger / accounting entry. The Salis Payment
Request it raises is a approval request record; Finance posts the actual
payment externally.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex_habitat.salis.salis_lib import log_activity


class RentalSettlement(Document):
    def validate(self):
        accrued = 0.0
        for row in self.vehicles:
            # Derive the line amount from days * daily_rate when not supplied.
            computed = flt(row.days) * flt(row.daily_rate)
            if not row.amount:
                row.amount = computed
            accrued += flt(row.amount)

        self.accrued_total = flt(accrued)
        self.variance = flt(self.claimed_total) - flt(self.accrued_total)

    def on_submit(self):
        log_activity(
            action="Rental Settlement Submitted",
            entity_type="Rental Settlement",
            entity_name=self.name,
            details={
                "rental_office": self.rental_office,
                "period_month": self.period_month,
                "accrued_total": self.accrued_total,
                "claimed_total": self.claimed_total,
                "variance": self.variance,
                "status": self.status,
            },
        )

    def on_cancel(self):
        log_activity(
            action="Rental Settlement Cancelled",
            entity_type="Rental Settlement",
            entity_name=self.name,
            details={"rental_office": self.rental_office, "period_month": self.period_month},
        )

    @frappe.whitelist()
    def create_payment_request(self):
        """Raise a finance-exclusive Salis Payment Request for this settlement.

        Posts NO GL: the Salis Payment Request is a approval request record
        that routes through the Finance approval gate. Idempotent — returns the
        existing linked request if one is already attached.
        """
        if self.docstatus != 1:
            frappe.throw(_("Submit the settlement before raising a payment request."))

        if self.payment_request and frappe.db.exists("Salis Payment Request", self.payment_request):
            return self.payment_request

        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Rental",
                "amount": flt(self.claimed_total) or flt(self.accrued_total),
                "status": "Draft",
                "rental_office": self.rental_office,
                "reference_doctype": "Rental Settlement",
                "reference_name": self.name,
                "remarks": _("Rental settlement {0} for period {1}.").format(
                    self.name, self.period_month
                ),
            }
        )
        pr.insert()

        self.db_set("payment_request", pr.name)
        log_activity(
            action="Rental Settlement Payment Request Raised",
            entity_type="Rental Settlement",
            entity_name=self.name,
            details={"payment_request": pr.name, "amount": pr.amount},
        )
        return pr.name
