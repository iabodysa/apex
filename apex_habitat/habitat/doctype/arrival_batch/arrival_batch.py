"""Arrival Batch controller.

A pre-arrival manifest: the workers a labour supplier expects to deliver to a
building on a date. The Arrivals Desk reconciles real arrivals against it, and
get_arrival_summary measures manifest completion from expected_count.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ArrivalBatch(Document):
    def validate(self) -> None:
        # expected_count drives the manifest-completion telemetry; keep it in sync
        # with the rows so the read endpoint never has to recount.
        self.expected_count = len(self.expected_workers or [])
        if not self.expected_count:
            frappe.throw(_("Add at least one expected worker to the manifest."))
        self.title = f"{self.building} - {frappe.utils.formatdate(self.expected_date)}"
