# Copyright (c) 2026, AFMCO and contributors
"""Unit guards for apex_core.utils.report_helpers.

Pure-Python (no live site). Proves date_range_condition() reproduces the verbatim
if/elif/elif block it replaced across the Salis/Habitat query reports, and that
plugging it into the caller pattern rebuilds each report's `conditions` dict
byte-identically to the pre-refactor literal.
"""

import unittest

from apex.apex_core.utils.report_helpers import date_range_condition


def _legacy_fragment(filters, from_key="from_date", to_key="to_date"):
    """The exact fragment the inline if/elif/elif blocks produced (oracle)."""
    if filters.get(from_key) and filters.get(to_key):
        return ["between", [filters[from_key], filters[to_key]]]
    elif filters.get(from_key):
        return [">=", filters[from_key]]
    elif filters.get(to_key):
        return ["<=", filters[to_key]]
    return None


class TestDateRangeCondition(unittest.TestCase):
    def test_both_bounds(self):
        f = {"from_date": "2026-01-01", "to_date": "2026-01-31"}
        self.assertEqual(
            date_range_condition(f, "attendance_date"),
            ["between", ["2026-01-01", "2026-01-31"]],
        )

    def test_from_only(self):
        f = {"from_date": "2026-01-01"}
        self.assertEqual(date_range_condition(f, "creation"), [">=", "2026-01-01"])

    def test_to_only(self):
        f = {"to_date": "2026-01-31"}
        self.assertEqual(date_range_condition(f, "log_date"), ["<=", "2026-01-31"])

    def test_neither_returns_none(self):
        self.assertIsNone(date_range_condition({}, "snapshot_date"))
        # empty strings are falsy — same as the original truthiness checks
        self.assertIsNone(date_range_condition({"from_date": "", "to_date": ""}, "creation"))

    def test_none_return_skips_key(self):
        # Caller pattern: a None result must leave the key ABSENT, not set to None.
        conditions = {}
        frag = date_range_condition({}, "movement_date")
        if frag is not None:
            conditions["movement_date"] = frag
        self.assertEqual(conditions, {})

    def test_custom_keys(self):
        f = {"start": "2026-02-01", "end": "2026-02-28"}
        self.assertEqual(
            date_range_condition(f, "d", from_key="start", to_key="end"),
            ["between", ["2026-02-01", "2026-02-28"]],
        )

    def test_matches_legacy_oracle_all_combos(self):
        combos = [
            {"from_date": "2026-01-01", "to_date": "2026-01-31"},
            {"from_date": "2026-01-01"},
            {"to_date": "2026-01-31"},
            {},
            {"from_date": "", "to_date": "2026-01-31"},
            {"from_date": "2026-01-01", "to_date": ""},
        ]
        for f in combos:
            self.assertEqual(
                date_range_condition(f, "x"),
                _legacy_fragment(f),
                msg=f"diverged from legacy block for filters={f}",
            )


class TestReportConditionsUnchanged(unittest.TestCase):
    """Rebuild representative reports' `conditions` dict via the helper and assert
    it equals the exact literal the pre-refactor inline block produced."""

    def _fleet_payment_register_filters(self, filters):
        # Mirror of fleet_payment_register.execute() filter-building.
        query_filters = {}
        if filters:
            for field in ("status", "expense_type", "company", "cost_center", "project"):
                if filters.get(field):
                    query_filters[field] = filters[field]
            date_condition = date_range_condition(filters, "creation")
            if date_condition is not None:
                query_filters["creation"] = date_condition
        return query_filters

    def _vehicle_utilisation_filters(self, filters):
        # Mirror of vehicle_utilisation.execute() filter-building (pre-scope).
        filters = filters or {}
        query_filters = {}
        if filters.get("vehicle"):
            query_filters["vehicle"] = filters["vehicle"]
        date_condition = date_range_condition(filters, "snapshot_date")
        if date_condition is not None:
            query_filters["snapshot_date"] = date_condition
        return query_filters

    def _lease_expiry_filters(self, filters):
        # Mirror of lease_expiry_watchlist.execute() filter-building.
        filters = filters or {}
        query_filters = {"docstatus": 1, "status": ["in", ["Approved", "Active"]]}
        if filters.get("building"):
            query_filters["building"] = filters["building"]
        date_condition = date_range_condition(filters, "lease_end_date")
        if date_condition is not None:
            query_filters["lease_end_date"] = date_condition
        return query_filters

    def test_fleet_payment_register(self):
        f = {"status": "Paid", "from_date": "2026-01-01", "to_date": "2026-03-31"}
        self.assertEqual(
            self._fleet_payment_register_filters(f),
            {"status": "Paid", "creation": ["between", ["2026-01-01", "2026-03-31"]]},
        )
        # no dates -> no creation key
        self.assertEqual(
            self._fleet_payment_register_filters({"company": "AFMCO"}),
            {"company": "AFMCO"},
        )

    def test_vehicle_utilisation(self):
        self.assertEqual(
            self._vehicle_utilisation_filters({"from_date": "2026-01-01"}),
            {"snapshot_date": [">=", "2026-01-01"]},
        )
        self.assertEqual(
            self._vehicle_utilisation_filters({"vehicle": "V-1", "to_date": "2026-06-01"}),
            {"vehicle": "V-1", "snapshot_date": ["<=", "2026-06-01"]},
        )
        self.assertEqual(self._vehicle_utilisation_filters(None), {})

    def test_lease_expiry_watchlist(self):
        self.assertEqual(
            self._lease_expiry_filters({}),
            {"docstatus": 1, "status": ["in", ["Approved", "Active"]]},
        )
        self.assertEqual(
            self._lease_expiry_filters({"building": "B-1", "from_date": "2026-01-01", "to_date": "2026-12-31"}),
            {
                "docstatus": 1,
                "status": ["in", ["Approved", "Active"]],
                "building": "B-1",
                "lease_end_date": ["between", ["2026-01-01", "2026-12-31"]],
            },
        )


if __name__ == "__main__":
    unittest.main()
