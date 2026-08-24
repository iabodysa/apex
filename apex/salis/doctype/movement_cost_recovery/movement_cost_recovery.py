# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float
from apex.salis.utils import set_financial_defaults

_OPERATIONS_ROLES = {"Fleet Manager", "System Manager"}


class MovementCostRecovery(Document):
    def validate(self):
        set_financial_defaults(self)
        if (self.amount or 0) <= 0:
            frappe.throw(_("Amount must be greater than zero."))
        if self.status == "Approved" and not self.basis_evidence:
            frappe.throw(_("Basis / Evidence is required before a recovery can be Approved."))
        if self.status in ("Approved", "Recovered") and not self.acknowledgement_received:
            frappe.throw(_("Acknowledgement Received must be set before a recovery can be {0}.").format(_(self.status)))
        self._derive_needs_operations()
        self._enforce_doa_gate()

    def _derive_needs_operations(self):
        threshold = get_salis_float("cost_recovery_ops_threshold", 1000.0)
        self.needs_operations = 1 if flt(self.amount) >= threshold else 0

    def _enforce_doa_gate(self):
        if self.status not in ("Approved", "Recovered") or not self.needs_operations:
            return
        if not (_OPERATIONS_ROLES & set(frappe.get_roles())):
            frappe.throw(
                _(
                    "This recovery reaches the Operations threshold and can only be approved by Operations-tier authority (Fleet Manager)."
                )
            )
