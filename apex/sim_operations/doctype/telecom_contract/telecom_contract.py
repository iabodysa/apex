# Copyright (c) 2026, AFMCO and contributors
"""Telecom Contract controller.

A submitted Telecom Contract is the authoritative, in-force agreement with one
supplier. ``status`` is server-derived (never hand-set): Draft while unsubmitted,
then Active or Expired from the contract period once submitted, and Terminated on
cancel. ``sim_count`` is a denormalized count refreshed from SIM Card's lifecycle.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class TelecomContract(Document):
    def validate(self):
        self._validate_dates()
        self._sync_status()

    def _validate_dates(self):
        if (
            self.contract_start_date
            and self.contract_end_date
            and getdate(self.contract_end_date) < getdate(self.contract_start_date)
        ):
            frappe.throw(_("Contract End Date cannot be earlier than Contract Start Date."))

    def _sync_status(self):
        """Derive ``status`` from submission state and the contract period.

        Draft while unsubmitted. Once submitted (docstatus 1), Active while the
        period is open, Expired once the end date has passed. Terminated is only
        reached on cancel and is never overwritten here.
        """
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
        # A cancelled contract is a terminated agreement.
        self.db_set("status", "Terminated")


def refresh_sim_count(contract: str | None) -> None:
    """Recompute a contract's denormalized ``sim_count`` from live SIM Cards.

    Called from SIM Card's own after_insert / on_update / on_trash so the count
    on the contract never drifts from the number of SIMs pointing at it. No-op
    when the contract no longer exists (e.g. deleted in the same transaction).
    """
    if not contract or not frappe.db.exists("Telecom Contract", contract):
        return
    count = frappe.db.count("SIM Card", {"telecom_contract": contract})
    frappe.db.set_value("Telecom Contract", contract, "sim_count", count, update_modified=False)
