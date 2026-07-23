# Copyright (c) 2026, AFMCO and contributors
"""Arrival Batch controller.

A pre-arrival manifest: the workers a labour supplier expects to deliver to a
building on a date. It is both a front-desk intake surface (suppliers submit it
via the public Arrival Manifest web form) and the backend record the Arrivals
Desk reconciles real arrivals against; get_arrival_summary measures manifest
completion from expected_count. Title and expected_count are derived in validate
and each row's "Arrived As" is set during reconciliation, so all three are
read-only by design.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


# [#7nku4t]
_MAX_EXPECTED_WORKERS = 500


class ArrivalBatch(Document):
    def validate(self) -> None:
        # [#eyhjls]
        self.expected_count = len(self.expected_workers or [])
        if not self.expected_count:
            frappe.throw(_("Add at least one expected worker to the manifest."))
        if self.expected_count > _MAX_EXPECTED_WORKERS:
            frappe.throw(
                _("A manifest can list at most {0} expected workers.").format(_MAX_EXPECTED_WORKERS)
            )
        self.title = f"{self.building} - {frappe.utils.formatdate(self.expected_date)}"

    @property
    def pending_arrival_count(self) -> int:
        # [#jyfszg]
        housed = frappe.db.count(
            "Housing Assignment",
            {
                "building": self.building,
                "check_in_date": self.expected_date,
                "docstatus": 1,
            },
        )
        return max(int(self.expected_count or 0) - housed, 0)
