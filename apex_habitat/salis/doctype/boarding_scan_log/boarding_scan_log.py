"""Boarding Scan Log — append-only audit row for one QR boarding-pass scan.

Each row records a single scan-validate attempt against a Dispatch Trip's QR
boarding pass: the outcome (``result``), the worker the pass identified, the
trip, and — on a valid first scan — the Trip Start Log row it created. The
operational headcount lives on Trip Start Log / Trip Boarding Event; this is the
immutable scan trail beside it (every attempt, including rejected ones, so a
duplicate or forged scan is visible).

No GL: like the rest of Salis it posts no accounting document. Rows are written
only by the scan endpoint (``salis.api.boarding``); the controller is thin and
keeps the audit honest — it stamps ``scanned_at`` and forbids editing a row once
written (a log is not a transaction).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class BoardingScanLog(Document):
    def before_insert(self):
        if not self.scanned_at:
            self.scanned_at = frappe.utils.now_datetime()

    def on_update(self):
        """An audit row is immutable after creation. Block any later edit so the
        scan trail cannot be rewritten; System Manager may still delete (correct a
        bad row), but never silently mutate one."""
        if not self.is_new() and not self.flags.in_insert:
            frappe.throw(_("Boarding Scan Log rows are append-only and cannot be edited."))
