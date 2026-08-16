# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Boarding Scan Register report.

Proves the ``result`` filter narrows the rows and that the four summary cards
(Scans / Valid / Failed Scans / Boarding Events Created) actually count what
their labels say, against a small set of Boarding Scan Log fixtures this test
owns (tagged via ``notes`` so it never touches rows written by anything else).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.boarding_scan_register.boarding_scan_register import execute


class TestBoardingScanRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.tag = f"A564-BSR-{frappe.generate_hash(length=8)}"
        self._rows = []
        for result, event_created in (
            ("Valid", 1),
            ("Valid", 1),
            ("Invalid Token", 0),
            ("Duplicate", 0),
        ):
            row = frappe.get_doc(
                {
                    "doctype": "Boarding Scan Log",
                    "result": result,
                    "boarding_event_created": event_created,
                    "notes": self.tag,
                }
            ).insert(ignore_permissions=True)
            self._rows.append(row.name)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in self._rows:
            frappe.delete_doc("Boarding Scan Log", name, force=True, ignore_permissions=True)

    def _my_rows(self, filters=None):
        columns, data, *_rest = execute(filters)
        return columns, [r for r in data if r.get("notes") == self.tag]

    def test_columns_declare_the_expected_fields(self):
        columns, _ = self._my_rows()
        fieldnames = {c["fieldname"] for c in columns}
        self.assertTrue({"scanned_at", "result", "driver", "boarding_event_created"} <= fieldnames)

    def test_unfiltered_returns_all_four_fixture_rows(self):
        _, rows = self._my_rows()
        self.assertEqual(len(rows), 4)

    def test_result_filter_narrows_to_matching_rows_only(self):
        columns, data, *_rest = execute({"result": "Valid"})
        mine = [r for r in data if r.get("notes") == self.tag]
        self.assertEqual(len(mine), 2)
        self.assertTrue(all(r["result"] == "Valid" for r in mine))

    def test_summary_cards_count_scans_valid_failed_and_events(self):
        _columns, _data, _msg, _chart, summary = execute({})
        by_label = {c["label"]: c["value"] for c in summary}
        # The site may carry other Boarding Scan Log rows from earlier tests, so
        # assert the summary counts are AT LEAST the fixture's own contribution
        # rather than an exact site-wide total.
        self.assertGreaterEqual(by_label["Scans"], 4)
        self.assertGreaterEqual(by_label["Valid"], 2)
        self.assertGreaterEqual(by_label["Failed Scans"], 2)
        self.assertGreaterEqual(by_label["Boarding Events Created"], 2)
