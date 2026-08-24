# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.company import resolve_company


class MovementCostTransfer(Document):
    def validate(self):
        self._set_company_default()
        if (self.amount or 0) <= 0:
            frappe.throw(_("Amount must be greater than zero."))
        self._validate_distinct_targets()
        self._stamp_approver()

    def _set_company_default(self):
        if not self.company:
            self.company = resolve_company("Salis")


    def _validate_distinct_targets(self):
        if self.from_project and self.to_project and self.from_project == self.to_project:
            frappe.throw(
                _("From Project and To Project must be different for a cost transfer.")
            )

        if (
            self.from_cost_center
            and self.to_cost_center
            and self.from_cost_center == self.to_cost_center
        ):
            frappe.throw(
                _("From Cost Center and To Cost Center must be different when both are set.")
            )

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user
