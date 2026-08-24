# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_live import notify_building

_MAX_EXPECTED_WORKERS = 500


class ArrivalBatch(Document):
    def validate(self) -> None:
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

        self._clear_guest_reconciliation_rows()
        self.expected_count = len(self.expected_workers or [])
        if self.expected_count > _MAX_EXPECTED_WORKERS:
            frappe.throw(
                _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
            )
        self.title = f"{self.building} - {frappe.utils.formatdate(self.expected_date)}"

    def _clear_guest_reconciliation_rows(self):
        if not (self.is_new() and frappe.session.user == "Guest"):
            return
        for row in self.expected_workers or []:
            row.temporary_worker = None

    def on_update(self):
        notify_building(self.building)

    @property
    def pending_arrival_count(self) -> int:
        housed = frappe.db.count(
            "Housing Assignment",
            {
                "building": self.building,
                "check_in_date": self.expected_date,
                "docstatus": 1,
            },
        )
        return max(int(self.expected_count or 0) - housed, 0)
