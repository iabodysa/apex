# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Logistay format adapters (P-197a).

Pure-Python: the parsers never touch frappe, so these run standalone
(``python3 -m unittest apex.logistay.test_format_adapters``) as well as under
``bench run-tests``. Every fixture is SELF-AUTHORED synthetic data - no real
client layout is used.

Each test proves the parser emits the exact ingestion contract the engine
consumes (``ingestion_engine`` docstring / lines 27-42):

    {period_month, rows:[{worker, tokens{}, daily[{day,token,ot}], header_total_days?}]}

and that a malformed / identity-less row is skipped, never raised (per-record
isolation, mirroring ``normalize_pending_intakes``).
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest

from apex.logistay import format_adapters as fa


def _assert_contract(test: unittest.TestCase, payload: dict) -> None:
    """Every payload must match the engine's structural contract."""
    test.assertIsInstance(payload, dict)
    test.assertIn("period_month", payload)
    test.assertIn("rows", payload)
    test.assertIsInstance(payload["rows"], list)
    for row in payload["rows"]:
        test.assertIn("worker", row)
        test.assertTrue(row["worker"])
        test.assertIsInstance(row["tokens"], dict)
        test.assertIsInstance(row["daily"], list)
        for cell in row["daily"]:
            test.assertEqual(set(cell), {"day", "token", "ot"})
            test.assertIsInstance(cell["day"], int)


class TestColumnGridAdapterA(unittest.TestCase):
    def test_named_columns_and_integer_day_headers(self):
        matrix = [
            ["Worker", "Role", "Payable Days", "1", "2", "3", "Total"],
            ["W-001", "Driver", "22", "P", "P", "A", "2"],
            ["2412345678", "Helper", "20", "P", "", "P", "2"],
        ]
        payload = fa.parse_intake("A", matrix, {"period_month": "2026-05"})
        _assert_contract(self, payload)
        self.assertEqual(payload["period_month"], "2026-05")
        self.assertEqual(len(payload["rows"]), 2)

        r0 = payload["rows"][0]
        self.assertEqual(r0["worker"], "W-001")
        self.assertEqual(r0["tokens"], {"Role": "Driver", "Payable Days": "22"})
        self.assertEqual(r0["daily"], [
            {"day": 1, "token": "P", "ot": 0},
            {"day": 2, "token": "P", "ot": 0},
            {"day": 3, "token": "A", "ot": 0},
        ])
        self.assertEqual(r0["header_total_days"], 2)
        # blank day cell dropped, iqama-style worker id preserved
        self.assertEqual([c["day"] for c in payload["rows"][1]["daily"]], [1, 3])

    def test_block_stacked_repeated_header_and_blank_rows_skipped(self):
        matrix = [
            ["Iqama", "1", "2"],
            ["2400000001", "P", "A"],
            [],                       # blank separator between blocks
            ["Iqama", "1", "2"],      # repeated header (block 2)
            ["2400000002", "A", "P"],
        ]
        payload = fa.parse_intake("A", matrix)
        _assert_contract(self, payload)
        self.assertEqual([r["worker"] for r in payload["rows"]],
                         ["2400000001", "2400000002"])

    def test_malformed_rows_isolated(self):
        matrix = [
            ["Worker", "Role", "1"],
            ["W-001", "Driver", "P"],
            ["", "Ghost", "P"],       # identity-less -> skipped
            ["W-002", "Helper", "A"],
        ]
        payload = fa.parse_intake("A", matrix)
        _assert_contract(self, payload)
        self.assertEqual([r["worker"] for r in payload["rows"]], ["W-001", "W-002"])

    def test_csv_round_trip(self):
        rows = [
            ["Worker", "Role", "1", "2"],
            ["W-009", "Driver", "P", "A"],
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grid.csv")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerows(rows)
            payload = fa.parse_intake("A", path)
        _assert_contract(self, payload)
        self.assertEqual(payload["rows"][0]["worker"], "W-009")
        self.assertEqual(len(payload["rows"][0]["daily"]), 2)


class TestMonthlyGridAdapterB(unittest.TestCase):
    def test_integer_day_headers(self):
        matrix = [
            ["Iqama", "1", "2", "3"],
            ["2400000010", "P", "P", "A"],
        ]
        payload = fa.parse_intake("B", matrix, {"period_month": "2026-06"})
        _assert_contract(self, payload)
        self.assertEqual(len(payload["rows"][0]["daily"]), 3)

    def test_positional_day_block_non_integer_headers(self):
        # weekday-letter headers: no integer day header, map positionally
        matrix = [
            ["Iqama", "Site", "Sat", "Sun", "Mon"],
            ["2400000020", "Riyadh", "P", "A", "P"],
        ]
        payload = fa.parse_intake("B", matrix, {"day_start_column": 2})
        _assert_contract(self, payload)
        row = payload["rows"][0]
        self.assertEqual(row["tokens"], {"Site": "Riyadh"})
        self.assertEqual([c["day"] for c in row["daily"]], [1, 2, 3])
        self.assertEqual([c["token"] for c in row["daily"]], ["P", "A", "P"])

    def test_xlsx_round_trip(self):
        import openpyxl

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "month.xlsx")
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["Iqama", "1", "2", "3"])
            ws.append(["2400000030", "P", "A", "P"])
            wb.save(path)
            payload = fa.parse_intake("B", path)
        _assert_contract(self, payload)
        self.assertEqual(payload["rows"][0]["worker"], "2400000030")
        self.assertEqual(len(payload["rows"][0]["daily"]), 3)


class TestPaperAdapter(unittest.TestCase):
    def test_keyed_rows_normalised(self):
        source = {
            "period_month": "2026-07",
            "rows": [
                {
                    "worker": "W-100",
                    "tokens": {"ts_role_package": "Driver", "ts_payable_days": 21},
                    "daily": [{"day": 1, "token": "P", "ot": 2}, {"day": 2, "token": "A"}],
                    "header_total_days": 21,
                },
                {"worker": "", "tokens": {}, "daily": []},   # identity-less -> skipped
                {"not": "a worker row"},                      # malformed -> skipped
            ],
        }
        payload = fa.parse_intake("PAPER", source)
        _assert_contract(self, payload)
        self.assertEqual(payload["period_month"], "2026-07")
        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        self.assertEqual(row["daily"][0], {"day": 1, "token": "P", "ot": 2})
        self.assertEqual(row["daily"][1], {"day": 2, "token": "A", "ot": 0})
        self.assertEqual(row["header_total_days"], 21)

    def test_bare_list_source(self):
        payload = fa.parse_intake("PAPER", [{"worker": "W-1", "daily": []}])
        _assert_contract(self, payload)
        self.assertEqual(payload["rows"][0]["worker"], "W-1")


class TestRegistryDispatch(unittest.TestCase):
    def test_known_codes_registered(self):
        self.assertEqual(fa.registered_codes(), ["A", "B", "PAPER"])

    def test_unknown_code_raises(self):
        with self.assertRaises(ValueError):
            fa.parse_intake("Z", [["Worker"]])

    def test_build_payload_json_is_valid_contract(self):
        raw = fa.build_payload_json("A", [["Worker", "1"], ["W-1", "P"]],
                                    {"period_month": "2026-05"})
        payload = json.loads(raw)
        _assert_contract(self, payload)
        self.assertEqual(payload["period_month"], "2026-05")


if __name__ == "__main__":
    unittest.main()
