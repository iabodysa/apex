# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

from apex.salis.utils import set_financial_defaults

_FINANCE_ROLES = {"Finance Manager", "System Manager"}

_FINANCE_GATED_STATUSES = {"Approved by Finance", "Paid"}

VALID_STATUSES = (
    "Draft",
    "Pending Finance",
    "Approved by Finance",
    "Paid",
    "Rejected",
    "Cancelled",
)


class SalisPaymentRequest(Document):
    def before_insert(self):
        if self.amended_from:
            self.linked_payment_doctype = None
            self.linked_payment_entry = None

    def validate(self):
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        if not self.requested_by:
            self.requested_by = frappe.session.user
        set_financial_defaults(self)
        if (self.amount or 0) <= 0:
            frappe.throw(_("Amount must be greater than zero."))
        self._enforce_finance_gate()


    def _old_status(self):
        previous = self.get_doc_before_save()
        return (previous.status if previous else None) or "Draft"

    def _enforce_finance_gate(self):
        new_status = self.status or "Draft"
        old_status = self._old_status()

        if new_status == old_status or new_status not in _FINANCE_GATED_STATUSES:
            return

        if not (_FINANCE_ROLES & set(frappe.get_roles())):
            frappe.throw(
                _("Only Finance can approve or mark a payment as paid. This step cannot be bypassed.")
            )

        if self.requested_by and frappe.session.user == self.requested_by:
            frappe.throw(
                _("You cannot approve or pay a Payment Request you raised; a different Finance approver is required.")
            )

        if not self.finance_approved_by:
            self.finance_approved_by = frappe.session.user
        if not self.finance_approved_on:
            self.finance_approved_on = now()
