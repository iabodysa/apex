# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from apex.salis.utils import set_financial_defaults

_RECONCILED_STATUSES = ("Reconciled", "Approved", "Closed")

_APPROVED_STATUSES = ("Approved", "Closed")

VALID_STATUSES = (
    "Draft",
    "Submitted to Movement",
    "Reconciled",
    "Approved",
    "Disputed",
    "Closed",
)


class FuelClaim(Document):
    def validate(self):
        if not self.requested_by:
            self.requested_by = frappe.session.user
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        if (self.claimed_litres or 0) <= 0:
            frappe.throw(_("Claimed Litres must be greater than zero."))
        set_financial_defaults(self)
        self._compute_consumption()
        self._compute_unit_price()
        self._stamp_reconciliation()
        self._guard_initial_status()

    def _compute_unit_price(self):
        litres = flt(self.claimed_litres)
        self.unit_price_per_litre = (
            flt(flt(self.claimed_amount) / litres, self.precision("unit_price_per_litre"))
            if litres
            else 0
        )

    def _stamp_reconciliation(self):
        if self.status in _RECONCILED_STATUSES:
            if not self.reconciled_on:
                self.reconciled_on = nowdate()
        else:
            self.reconciled_on = None

        if self.status in _APPROVED_STATUSES:
            if not self.approved_by:
                self.approved_by = frappe.session.user
        else:
            self.approved_by = None


    def _compute_consumption(self):
        consumed = 0.0
        if self.vehicle and self.period_month:
            rows = frappe.get_all(
                "Fuel Consumption Ledger",
                filters={"vehicle": self.vehicle, "period_month": self.period_month},
                fields=["litres"],
            )
            consumed = sum((row.litres or 0) for row in rows)

        self.consumed_litres = consumed
        self.variance_litres = (self.claimed_litres or 0) - consumed

    def _guard_initial_status(self):
        if self.is_new() and self.status and self.status != "Draft":
            frappe.throw(
                _("A Fuel Claim must be created with status Draft; {0} is reached through the workflow.").format(
                    _(self.status)
                )
            )
