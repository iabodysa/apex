# Copyright (c) 2026, AFMCO and contributors
"""Invoice Assembly Run controller - groups the up-to-4 Sales Invoices from one
POSTED Reconciliation Run (D8 four-way split).

Thin by design: stock ERPNext Sales Invoice computes every amount/tax/total, so
this controller only guards the Separation-of-Duties invariant that the amount
and issue-gate logic (``logistay.invoice_assembly``) relies on. The DoA band,
naming gate, and issuance block are enforced at Sales Invoice ``before_submit``,
not here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class InvoiceAssemblyRun(Document):
    def validate(self) -> None:
        self._guard_sod_distinct()

    def _guard_sod_distinct(self) -> None:
        # SoD: the assembler may not also be the approver/issuer.
        if (
            self.inv_prepared_by
            and self.inv_approved_by
            and self.inv_prepared_by == self.inv_approved_by
        ):
            frappe.throw(_("Preparer and approver must differ (SoD)."))
