# Copyright (c) 2026, afmcoltd
"""Freelancer controller.

A Freelancer is a short-term contract worker on a fixed monthly salary
with no car and no allowances. They exist in the thousands with high yearly
churn, and are recorded in ACCOUNTING as a party so the monthly salary is paid
through a native ERPNext Payment Entry — no custom GL/posting code lives here.

This is an Employee-lite master and is intentionally SEPARATE from the housing
``Temporary Worker``: that doctype is the housing/custody identity carried by the
non-accounting ``party_type``/``party`` Dynamic Link (see
``apex_core.utils.party_link``). The accounting party axis built here (a custom
ERPNext Party Type "Freelancer") is a different axis and the two are kept apart.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, nowdate
from frappe.model.document import Document

from apex.apex_core.utils.ledger_index import add_unique_guarded


class Freelancer(Document):
    def validate(self) -> None:
        """Validates the contract window and salary, then derives status from the contract end date."""
        self._validate_contract_window()
        self._validate_salary()
        self._derive_status()

    def _validate_contract_window(self) -> None:
        """Blocks a contract end date that is not after the contract start date."""
        if not (self.contract_start_date and self.contract_end_date):
            return
        if getdate(self.contract_end_date) <= getdate(self.contract_start_date):
            frappe.throw(_("Contract End Date must be after Contract Start Date."))

    def _validate_salary(self) -> None:
        """Blocks a monthly salary that is zero or negative."""
        if not self.monthly_salary or self.monthly_salary <= 0:
            frappe.throw(_("Monthly Salary must be greater than zero."))

    def _derive_status(self) -> None:
        """Marks status Expired once the contract end date has passed, unless already Terminated."""
        if self.status == "Terminated":
            return
        if self.contract_end_date and getdate(self.contract_end_date) < getdate(nowdate()):
            self.status = "Expired"


def on_doctype_update():
    """Adds a unique database constraint on the national ID or Iqama number field."""
    add_unique_guarded(
        "Freelancer",
        ["national_id_or_iqama"],
        constraint_name="uq_freelancer_national_id",
    )
