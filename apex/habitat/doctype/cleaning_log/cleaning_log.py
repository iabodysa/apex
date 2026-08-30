# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

from apex.habitat.cleaning_engine import post_cleaning_compliance, reverse_cleaning_compliance

REQUIRED_AREAS = ("Bathrooms", "Kitchen", "Corridors")


class CleaningLog(Document):
    def before_submit(self):
        self._stamp_area_evidence()
        self._validate_area_evidence()

    def on_submit(self):
        post_cleaning_compliance(self)

    def on_cancel(self):
        reverse_cleaning_compliance(self.name)

    def _stamp_area_evidence(self):
        for row in self.get("area_photos") or []:
            if row.photo and not row.captured_at:
                row.captured_at = now()
            if row.photo and not row.captured_by:
                row.captured_by = frappe.db.get_value(
                    "Employee", {"user_id": frappe.session.user}, "name"
                )

    def _validate_area_evidence(self):
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
    frappe.db.add_unique(
        "Cleaning Log",
        ["building", "cleaning_date", "docstatus"],
        "unique_cleaning_log_building_date_status",
    )
