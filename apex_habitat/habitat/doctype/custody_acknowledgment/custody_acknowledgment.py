# Copyright (c) 2026, AFMCO and contributors
"""Custody Acknowledgment controller.

Records a holder's receipt confirmation for a Custody Issue. Written from the
My Custody Acknowledgment Web Form; the acknowledgment lives on its own target
(not on the Custody Issue itself). Validation is a class method so it fires
without a doc_events hook.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class CustodyAcknowledgment(Document):
    def validate(self):
        # Only submitted issues can be acknowledged as received.
        docstatus = frappe.db.get_value("Custody Issue", self.custody_issue, "docstatus")
        if docstatus != 1:
            frappe.throw(
                _("Custody Issue {0} must be submitted before it can be acknowledged.").format(self.custody_issue)
            )

        # Either the typed confirmation OR the signature fallback must be present.
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
