"""Rental Settlement controller.

Monthly reconciliation of a Rental Office's claim against accrued rental days.
``validate`` recomputes ``accrued_total`` from the vehicle lines (and the line
amounts themselves) and the ``variance`` against the claimed total. On submit,
``create_payment_request`` may raise a finance-exclusive Salis Payment Request
(expense_type "Rental") referencing this settlement.

Status transitions are owned by the native **Rental Settlement Workflow** (see
``salis/workflow/rental_settlement_workflow/``), not by this controller. In
particular the "Mark Paid" transition is restricted to the **Finance Manager**
role and carries the Segregation-of-Duties condition ``requested_by !=
session.user`` so the finance approver can never be the (server-stamped)
requester. This controller keeps only the *data* guards (totals, variance, the
known-status check) and the server-side requester stamp that the SoD gate
relies on.

This controller posts NO General Ledger / accounting entry. The Salis Payment
Request it raises is a payment request record; Finance posts the actual
payment externally.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

VALID_STATUSES = (
    "Draft",
    "Reconciled",
    "Approved",
    "Paid",
    "Disputed",
    "Cancelled",
)


class RentalSettlement(Document):
    def before_insert(self):
        # Stamp the requester server-side (read-only field) so the
        # segregation-of-duties / maker-checker gate cannot be spoofed.
        if not self.requested_by:
            self.requested_by = frappe.session.user

    def validate(self):
        # The Select still carries the known states for filtering/colour, but the
        # Rental Settlement Workflow owns *transitions* — this only rejects an
        # unknown value.
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        if not self.requested_by:
            self.requested_by = frappe.session.user
        if not self.company:
            from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
                get_default_company,
            )

            self.company = get_default_company()

        accrued = 0.0
        for row in self.vehicles:
            # Derive the line amount from days * daily_rate when not supplied.
            computed = flt(row.days) * flt(row.daily_rate)
            if not row.amount:
                row.amount = computed
            accrued += flt(row.amount)

        self.accrued_total = flt(accrued)
        self.variance = flt(self.claimed_total) - flt(self.accrued_total)

    # Submit/cancel are recorded natively (Version track_changes + auto-comment).

    @frappe.whitelist(methods=["POST"])
    def create_payment_request(self):
        """Raise a finance-exclusive Salis Payment Request for this settlement.

        Posts NO GL: the Salis Payment Request is a payment request record
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
        self.add_comment(
            "Info",
            _("Payment Request {0} raised for {1} SAR.").format(pr.name, pr.amount),
        )
        return pr.name
