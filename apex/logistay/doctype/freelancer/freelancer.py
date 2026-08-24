# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, nowdate
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class Freelancer(Document):
    def validate(self) -> None:
        self._validate_contract_window()
        self._validate_salary()
        self._derive_status()

    def _validate_contract_window(self) -> None:
        if not (self.contract_start_date and self.contract_end_date):
            return
        if getdate(self.contract_end_date) <= getdate(self.contract_start_date):
            frappe.throw(_("Contract End Date must be after Contract Start Date."))

    def _validate_salary(self) -> None:
        if not self.monthly_salary or self.monthly_salary <= 0:
            frappe.throw(_("Monthly Salary must be greater than zero."))

    def _derive_status(self) -> None:
        if self.status == "Terminated":
            return
        if self.contract_end_date and getdate(self.contract_end_date) < getdate(nowdate()):
            self.status = "Expired"


def on_doctype_update():
    add_unique_guarded(
        "Freelancer",
        ["national_id_or_iqama"],
        constraint_name="uq_freelancer_national_id",
    )
