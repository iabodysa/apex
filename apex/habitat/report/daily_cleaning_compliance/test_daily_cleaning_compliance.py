# Copyright (c) 2026, AFMCO and contributors

"""Tests for the Daily Cleaning Compliance report.

The load-bearing guarantee: the report reads the compliance fact from the
immutable Cleaning Compliance Ledger, so a historical compliance value does NOT
change when the source Cleaning Log is later cancelled/amended. A cancel posts a
negating reversal (both rows flagged is_cancelled) so the cancelled log nets out
of the LIVE window, but a value snapshotted from a window that predates the
cancel is reproducible — non-retroactivity.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.report.daily_cleaning_compliance.daily_cleaning_compliance import execute


class TestDailyCleaningCompliance(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"DCC Bldg {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name

        # Two rooms so the compliance denominator is 2 (one cleaned, one skipped
        # -> a stable 50% the report must reproduce from the ledger).
        self.room_a = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.building,
                "room_number": f"DCC-A-{tag}",
            }
        ).insert(ignore_permissions=True).name
        self.room_b = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.building,
                "room_number": f"DCC-B-{tag}",
            }
        ).insert(ignore_permissions=True).name

    def _submit_log(self):
        doc = frappe.get_doc(
            {
                "doctype": "Cleaning Log",
                "naming_series": "CLEAN-.YYYY.-.####",
                "building": self.building,
                "cleaning_date": today(),
                "room_details": [
                    {"room": self.room_a, "room_status": "Cleaned", "cleaned": 1},
                    {"room": self.room_b, "room_status": "Skipped", "skip_reason": "Locked"},
                ],
                "area_photos": [
                    {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/dcc-bath.jpg"},
                    {"area": "Kitchen", "status": "Cleaned", "photo": "/files/dcc-kitchen.jpg"},
                    {"area": "Corridors", "status": "N/A", "note": "No corridor"},
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def _row_for_log(self, log_name):
        _columns, data = execute({"date_from": today(), "date_to": today(), "building": self.building})
        return next((r for r in data if r["name"] == log_name), None)

    def test_compliance_value_is_stable_after_source_cancelled(self):
        """The historical compliance fact must not change when the source log is
        cancelled — the report reads the immutable ledger, not the mutable log."""
        log = self._submit_log()

        before = self._row_for_log(log.name)
        self.assertIsNotNone(before, "the submitted log must appear in the report")
        # 1 of 2 rooms cleaned (the Skipped room is never compliant) -> 50%.
        self.assertEqual(before["rooms_total"], 2)
        self.assertEqual(before["rooms_cleaned"], 1)
        self.assertEqual(before["compliance_pct"], 50.0)

        # Cancel the source: a mutable report would now show a different (or empty)
        # value. The ledger posts a reversal flagging both rows is_cancelled, so the
        # live window nets the log out -> it must disappear from the live report,
        # while the ledger ORIGINAL row (the historical fact) is preserved for audit.
        log.cancel()

        after = self._row_for_log(log.name)
        self.assertIsNone(
            after,
            "a cancelled log nets out of the live compliance window (reversed, not deleted)",
        )

        # Non-retroactivity proof: the ORIGINAL ledger fact still exists unchanged
        # (preserved for audit) — the cancel reversed via a mirror row, never
        # rewrote or deleted the snapshotted compliance fact.
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

    def test_report_reads_from_ledger_not_live_log(self):
        """The numerator/denominator come from the ledger: a direct edit of the
        live Cleaning Log Room Detail rows (bypassing a re-post) must NOT change
        the reported compliance, because the report never reads the child rows."""
        log = self._submit_log()
        before = self._row_for_log(log.name)
        self.assertEqual(before["compliance_pct"], 50.0)

        # Tamper with the live child rows directly (no re-submit, so no re-post):
        # flip the skipped room's cleaned flag on the live doc's DB row.
        skipped = next(r for r in log.room_details if r.room == self.room_b)
        frappe.db.set_value("Cleaning Log Room Detail", skipped.name, "cleaned", 1)

        after = self._row_for_log(log.name)
        self.assertEqual(
            after["compliance_pct"], 50.0,
            "compliance is read from the immutable ledger, not the mutated child row",
        )
