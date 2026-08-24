# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from apex.apex_core.utils.vat import apply_vat


class TelecomContract(Document):
    def validate(self):
        self._validate_dates()
        self._sync_status()
        apply_vat(self, self.recurring_amount)

    def _validate_dates(self):
        if (
            self.contract_start_date
            and self.contract_end_date
            and getdate(self.contract_end_date) < getdate(self.contract_start_date)
        ):
            frappe.throw(_("Contract End Date cannot be earlier than Contract Start Date."))

    def _sync_status(self):
        if self.docstatus == 0:
            self.status = "Draft"
            return
        if self.docstatus == 1 and self.status != "Terminated":
            self.status = (
                "Expired"
                if self.contract_end_date and getdate(self.contract_end_date) < getdate(today())
                else "Active"
            )

    def on_cancel(self):
        self.db_set("status", "Terminated")


def refresh_sim_count(contract: str | None) -> None:
    if not contract or not frappe.db.exists("Telecom Contract", contract):
        return
    count = frappe.db.count("SIM Card", {"telecom_contract": contract})
    frappe.db.set_value("Telecom Contract", contract, "sim_count", count, update_modified=False)
