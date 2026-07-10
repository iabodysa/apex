# Copyright (c) 2026, AFMCO and contributors

"""Tests for the Housing Cleaning Audit report.

The load-bearing guarantee: the rooms_cleaned column is the posted cleaned-room
count read from the immutable Cleaning Compliance Ledger, so a historical
rooms_cleaned value does NOT change when the source Cleaning Log's child rows are
later edited, and the original posted fact survives a source cancel. A cancel
posts a negating reversal (both rows flagged is_cancelled) so the cancelled log
nets out of the LIVE count, but the original ledger fact is preserved for audit —
non-retroactivity.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.habitat.report.housing_cleaning_audit.housing_cleaning_audit import execute


class TestHousingCleaningAudit(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"HCA Bldg {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        # Two rooms: one cleaned, one skipped -> a stable rooms_cleaned of 1 that
        # the report must reproduce from the ledger.
        self.room_a = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.building,
                "room_number": f"HCA-A-{tag}",
            }
        ).insert(ignore_permissions=True).name
        self.room_b = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.building,
                "room_number": f"HCA-B-{tag}",
            }
        ).insert(ignore_permissions=True).name

    def _submit_log(self):
        doc = frappe.get_doc(
            {
                "doctype": "Cleaning Log",
                "naming_series": "CLEAN-.YYYY.-.####",
                "building": self.building,
                "cleaning_date": today(),
                "supervisor_approved": 1,
                "room_details": [
                    {"room": self.room_a, "room_status": "Cleaned", "cleaned": 1},
                    {"room": self.room_b, "room_status": "Skipped", "skip_reason": "Locked"},
                ],
                "area_photos": [
                    {"area": "Bathrooms", "status": "N/A", "note": "test fixture"},
                    {"area": "Kitchen", "status": "N/A", "note": "test fixture"},
                    {"area": "Corridors", "status": "N/A", "note": "test fixture"},
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def _row_for_log(self, log_name, building):
        _columns, data = execute({"from_date": today(), "to_date": today(), "building": building})[:2]
        # The real (non-synthetic) row is the one whose building matches and whose
        # rooms_cleaned was sourced from the ledger; match on building + a non-Missed
        # status (the live log row), since synthetic gap rows carry Missed/0.
        return next(
            (r for r in data if r["building"] == building and r["status"] != "Missed"),
            None,
        )

    def test_rooms_cleaned_is_stable_after_child_rows_tampered(self):
        """rooms_cleaned is read from the immutable ledger: a direct edit of the
        live Cleaning Log Room Detail rows (bypassing a re-post) must NOT change
        the reported count, because the report never reads the child rows."""
        log = self._submit_log()

        before = self._row_for_log(log.name, self.building)
        self.assertIsNotNone(before, "the submitted log must appear in the report")
        self.assertEqual(before["rooms_cleaned"], 1)

        # Tamper with the live child rows directly (no re-submit, so no re-post):
        # flip the skipped room's cleaned flag on the live doc's DB row.
        skipped = next(r for r in log.room_details if r.room == self.room_b)
        frappe.db.set_value("Cleaning Log Room Detail", skipped.name, "cleaned", 1)

        after = self._row_for_log(log.name, self.building)
        self.assertEqual(
            after["rooms_cleaned"], 1,
            "rooms_cleaned is read from the immutable ledger, not the mutated child row",
        )

    def test_original_posted_fact_preserved_after_source_cancelled(self):
        """The original ledger cleaned-room fact must survive a source cancel — the
        cancel reverses via a mirror row, it never rewrites or deletes the fact."""
        log = self._submit_log()

        before = self._row_for_log(log.name, self.building)
        self.assertEqual(before["rooms_cleaned"], 1)

        # Cancel the source: the ledger posts a reversal flagging both rows
        # is_cancelled, so the log nets out of the LIVE count.
        log.cancel()

        # Non-retroactivity proof: the ORIGINAL ledger fact still exists unchanged
        # (preserved for audit).
        originals = frappe.get_all(
            "Cleaning Compliance Ledger",
            filters={"cleaning_log": log.name, "reversal_of": ["is", "not set"]},
            fields=["cleaned"],
        )
        self.assertEqual(len(originals), 2, "both original per-room facts are preserved")
        self.assertEqual(
            sum(1 for r in originals if r.cleaned), 1,
            "the original cleaned-room fact is unchanged after the source cancel",
        )
