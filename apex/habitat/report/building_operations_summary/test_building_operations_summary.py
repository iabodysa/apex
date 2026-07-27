# Copyright (c) 2026, AFMCO and contributors
"""The Safety Inspections column must not empty when its writer retires.

``_safety_inspections`` counted submitted Safety Inspection Reports only. That
record is deprecated and nothing produces a new one, so left alone the column
would have read 0 for every building in every period after the cutover -- a
report asserting the estate was never checked, which no gate would have called a
failure because the query still ran and still returned rows (none).

It now counts BOTH records: Safety Round for the live flow, the legacy report so
a pre-cutover window keeps its history. Both legs are asserted, because dropping
either one is the silent failure this exists to catch.

Query-shaped by design (frappe.get_all is stubbed) rather than fixture-built: the
function is a two-query summation, and the thing that breaks is WHICH doctype and
WHICH date column it asks for. It follows test_housing_supervisor_scope.py, which
already exercises this report's scoping the same way. It needs no SITE, but it is
not frappe-free — the report module imports frappe — so it claims no standalone
run and stays a suite test.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from apex.habitat.report.building_operations_summary import (
    building_operations_summary as R,
)

BUILDINGS = ["BLDG-1", "BLDG-2"]
WINDOW = ("2026-07-01", "2026-07-31")

# One submitted record of each kind, so a leg that is dropped changes the count.
ROWS = {
    "Safety Round": [{"building": "BLDG-1"}, {"building": "BLDG-1"}],
    "Safety Inspection Report": [{"building": "BLDG-1"}, {"building": "BLDG-2"}],
}


class _Recorder:
    """Stands in for frappe.get_all, recording (doctype, filters) per call.

    Returns frappe._dict rows, not plain dicts: the caller reads ``r.building``,
    and a plain dict would fail on attribute access rather than exercising it."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, doctype, filters=None, fields=None, **_kwargs):
        self.calls.append((doctype, filters or {}))
        return [frappe._dict(row) for row in self.rows.get(doctype, [])]

    def filters_for(self, doctype):
        return next((f for dt, f in self.calls if dt == doctype), None)


class TestSafetyInspectionsColumn(unittest.TestCase):
    def _run(self, rows=None):
        recorder = _Recorder(ROWS if rows is None else rows)
        with patch("frappe.get_all", recorder):
            return recorder, R._safety_inspections(BUILDINGS, *WINDOW)

    def test_counts_both_the_live_round_and_the_legacy_report(self):
        recorder, counts = self._run()
        self.assertEqual(
            [dt for dt, _f in recorder.calls],
            ["Safety Round", "Safety Inspection Report"],
            "the column must read the live record AND the deprecated one; reading "
            "only the deprecated one empties as its writer retires, reading only "
            "the live one erases every pre-cutover period",
        )
        self.assertEqual(counts["BLDG-1"], 3, "the two legs must sum, not overwrite")
        self.assertEqual(counts["BLDG-2"], 1)

    def test_each_record_is_windowed_on_its_own_date_column(self):
        """Safety Round dates on round_date, the legacy report on inspection_date.
        Reusing one field name would filter on a column the other does not have."""
        recorder, _counts = self._run()
        expected = ["between", [WINDOW[0], WINDOW[1]]]
        round_filters = recorder.filters_for("Safety Round")
        self.assertEqual(round_filters.get("round_date"), expected)
        self.assertNotIn("inspection_date", round_filters)
        legacy_filters = recorder.filters_for("Safety Inspection Report")
        self.assertEqual(legacy_filters.get("inspection_date"), expected)
        self.assertNotIn("round_date", legacy_filters)

    def test_only_submitted_records_in_the_scoped_buildings_are_counted(self):
        recorder, _counts = self._run()
        for doctype, filters in recorder.calls:
            self.assertEqual(filters.get("docstatus"), 1, f"{doctype}: draft rows counted")
            self.assertEqual(
                filters.get("building"),
                ["in", BUILDINGS],
                f"{doctype}: frappe.get_all forces ignore_permissions, so the "
                "caller's building scope is the ONLY thing confining this read",
            )

    def test_a_building_with_no_safety_record_reads_zero_not_a_key_error(self):
        _recorder, counts = self._run(rows={})
        self.assertEqual(counts["BLDG-1"], 0)


if __name__ == "__main__":
    unittest.main()
