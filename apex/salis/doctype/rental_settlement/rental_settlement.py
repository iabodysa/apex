# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, now_datetime

from apex.apex_core.utils.company import display_currency, resolve_company

from apex.apex_core.utils.vat import apply_vat
from apex.salis.rental_engine import linked_accrued_total, release_settlement, stamp_settlement

VALID_STATUSES = (
    "Draft",
    "Reconciled",
    "Approved",
    "Paid",
    "Disputed",
    "Cancelled",
)

SETTLED_STATUSES = ("Approved", "Paid")


class RentalSettlement(Document):
    def validate(self):
        self._guard_duplicate()
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        if not self.requested_by:
            self.requested_by = frappe.session.user
        if not self.company:
            self.company = resolve_company("Salis")

        accrued = 0.0
        derive_line_amounts = self.docstatus == 0
        stored_rows = self._stored_vehicle_rows()
        for row in self.vehicles:
            computed = flt(row.days) * flt(row.daily_rate)
            if derive_line_amounts and self._amount_was_derived(row, stored_rows):
                row.amount = computed
            accrued += flt(row.amount)

        ledger_total = linked_accrued_total(self.rental_office, self.period_month)
        self.ledger_accrued_total = flt(ledger_total)

        self.accrued_from_ledger = 0
        if self.vehicles:
            self.accrued_total = flt(accrued)
        else:
            self.accrued_total = flt(ledger_total)
            self.accrued_from_ledger = 1

        self.ledger_variance = flt(self.accrued_total) - flt(ledger_total)
        self.variance = flt(self.claimed_total) - flt(self.accrued_total)

        apply_vat(self, self.claimed_total)
        self._stamp_approval()

    def _guard_duplicate(self):
        if not (self.rental_office and self.period_month):
            return
        duplicate = frappe.db.exists(
            "Rental Settlement",
            {
                "rental_office": self.rental_office,
                "period_month": self.period_month,
                "docstatus": ["<", 2],
                "name": ["!=", self.name or ""],
            },
        )
        if duplicate:
            frappe.throw(
                _("Rental Settlement {0} already covers office {1} for period {2}.").format(
                    duplicate, self.rental_office, self.period_month
                )
            )

    def _stored_vehicle_rows(self):
        before = self.get_doc_before_save()
        return {row.name: row for row in (before.vehicles if before else [])}

    @staticmethod
    def _amount_was_derived(row, stored_rows):
        if row.amount is None:
            return True
        stored = stored_rows.get(row.name)
        if stored is None:
            return False
        return flt(stored.amount) == flt(stored.days) * flt(stored.daily_rate)

    def _stamp_approval(self, persist=False):
        approved = self.status in SETTLED_STATUSES
        if approved and not self.approved_by:
            approved_by, approved_on = frappe.session.user, now_datetime()
        elif approved:
            approved_by, approved_on = self.approved_by, self.approved_on or now_datetime()
        else:
            approved_by, approved_on = None, None

        if persist:
            self.db_set("approved_by", approved_by)
            self.db_set("approved_on", approved_on)
            return
        self.approved_by = approved_by
        self.approved_on = approved_on

    def on_submit(self):
        self._sync_accrual_stamp()

    def on_update_after_submit(self):
        self._sync_accrual_stamp()
        self._stamp_approval(persist=True)

    def on_cancel(self):
        release_settlement(self.name)

    def _sync_accrual_stamp(self):
        if self.status not in SETTLED_STATUSES:
            return
        stamp_settlement(self.name, self.rental_office, self.period_month)

    @frappe.whitelist(methods=["POST"])
    def create_payment_request(self):
        if self.docstatus != 1:
            frappe.throw(_("Submit the settlement before raising a payment request."))

        if self.status != "Approved":
            frappe.throw(
                _(
                    "A payment request can only be raised on an Approved settlement "
                    "(current status: {0})."
                ).format(_(self.status))
            )

        if self.payment_request and frappe.db.exists("Salis Payment Request", self.payment_request):
            return self.payment_request

        claimed = flt(self.claimed_total)
        reconciled = flt(self.accrued_total)
        payable = min(claimed, reconciled) if claimed else reconciled

        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Rental",
                "amount": payable,
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
            _("Payment Request {0} raised for {1}.").format(
                pr.name, fmt_money(pr.amount, currency=display_currency("Salis"))
            ),
        )
        return pr.name
