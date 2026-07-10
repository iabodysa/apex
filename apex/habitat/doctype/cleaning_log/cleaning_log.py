# Copyright (c) 2026, AFMCO and contributors
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

# Common areas the client audit always checks; each must be evidenced before submit.
REQUIRED_AREAS = ("Bathrooms", "Kitchen", "Corridors")


class CleaningLog(Document):
    def before_submit(self):
        self._stamp_area_evidence()
        self._validate_area_evidence()

    def on_submit(self):
        # Post the immutable per-room Cleaning Compliance Ledger (system-written
        # audit memo). Idempotent, so a re-submit of an amended log never doubles.
        from apex.habitat.cleaning_engine import post_cleaning_compliance

        post_cleaning_compliance(self)

    def on_cancel(self):
        # Reverse (negative mirror + is_cancelled) the rows this log posted so a
        # cancelled/amended log nets out of every compliance sum; never deletes.
        from apex.habitat.cleaning_engine import reverse_cleaning_compliance

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
                row.captured_by = _session_employee()

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


def _session_employee() -> str | None:
    """Resolve the current session user to their Employee, if any."""
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
