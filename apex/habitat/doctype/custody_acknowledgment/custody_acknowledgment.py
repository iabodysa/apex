# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class CustodyAcknowledgment(Document):
    def validate(self):
        docstatus = frappe.db.get_value("Custody Issue", self.custody_issue, "docstatus")
        if docstatus != 1:
            frappe.throw(
                _("Custody Issue {0} must be submitted before it can be acknowledged.").format(self.custody_issue)
            )

        if self.confirmation_method == "Signature":
            if not self.signature:
                frappe.throw(
                    _("Please sign to acknowledge receipt, or choose Confirmed Receipt and tick the confirmation.")
                )
        elif not self.receipt_confirmed:
            frappe.throw(
                _("Please tick the receipt confirmation, or choose Signature and sign instead.")
            )

        self.acknowledged_on = self.acknowledged_on or now_datetime()
