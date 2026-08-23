# Copyright (c) 2026, afmcoltd
"""Cleaning Log controller.

The mandatory-evidence gate is the Document.before_submit class method (Frappe
calls it natively on submit; no hooks.py doc_events entry is needed). Submitting
is the audit-evidence commit: docstatus immutability makes the photo record
tamper-evident for the client sanitation/housing audit file.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

from apex.apex_core.utils.ledger_index import add_unique_guarded
from apex.habitat.cleaning_engine import post_cleaning_compliance, reverse_cleaning_compliance

REQUIRED_AREAS = ("Bathrooms", "Kitchen", "Corridors")


class CleaningLog(Document):
    def before_submit(self):
        """Stamps missing photo evidence fields then blocks submission when a required area lacks proof."""
        self._stamp_area_evidence()
        self._validate_area_evidence()

    def on_submit(self):
        """Posts the cleaning log's room results to the Cleaning Compliance Ledger."""
        post_cleaning_compliance(self)

    def on_cancel(self):
        """Reverses the cleaning log's posted Cleaning Compliance Ledger entries."""
        reverse_cleaning_compliance(self.name)

    def _stamp_area_evidence(self):
        """Server-stamp who/when on any photo row that arrived unstamped.

        The captured_at/captured_by floor must come from the server, never the
        client, so the audit evidence cannot be back-dated or spoofed.
        """
        for row in self.get("area_photos") or []:
            if row.photo and not row.captured_at:
                row.captured_at = now()
            if row.photo and not row.captured_by:
                row.captured_by = frappe.db.get_value(
                    "Employee", {"user_id": frappe.session.user}, "name"
                )

    def _validate_area_evidence(self):
        """Each required area needs a Cleaned photo, or a Not Cleaned / N/A note."""
        rows_by_area: dict[str, list] = {}
        for row in self.get("area_photos") or []:
            rows_by_area.setdefault(row.area, []).append(row)

        for area in REQUIRED_AREAS:
            rows = rows_by_area.get(area) or []
            if not rows:
                frappe.throw(
                    _("Area evidence for {0} is required before submit.").format(_(area))
                )
            cleaned_with_photo = any(r.status == "Cleaned" and r.photo for r in rows)
            excused_with_note = any(
                r.status in ("Not Cleaned", "N/A") and (r.note or "").strip() for r in rows
            )
            if not (cleaned_with_photo or excused_with_note):
                frappe.throw(
                    _(
                        "Area {0} must have a Cleaned photo, or be marked Not Cleaned / N/A with a note."
                    ).format(_(area))
                )


def on_doctype_update():
    """DB-level backstop for the app-level 'one non-cancelled log per (building,
    cleaning_date)' guard.

    ``daily_cleaning_log_generator`` writes Cleaning Logs from the scheduler with only
    a check-then-insert ``frappe.db.exists`` guard, and any second writer enqueued
    beside it can pass its 'not exists yet' check for the same building/day before
    either commits, and double-create. That is what a check-then-insert cannot prevent
    and an index can, whatever the number of writers. This composite UNIQUE
    index makes the second insert fail at the DB instead. ``docstatus`` is part of
    the key (mirroring the app guard's ``docstatus != 2`` filter and the Scheduled
    Task Instance precedent) so a cancelled log never blocks re-logging the same
    building/day. Idempotent + duplicate-safe via ``add_unique_guarded``.
    """
    add_unique_guarded(
        "Cleaning Log",
        ["building", "cleaning_date", "docstatus"],
        "unique_cleaning_log_building_date_status",
    )
