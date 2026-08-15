# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Clearance Register report execute().

Asserts the column contract and that execute() runs end-to-end (project scope
unrestricted for Administrator) returning a data list whose rows carry every
declared field. Requires a live site (queries Driver Clearance).

The row test seeds an open clearance: on an empty test database the per-row loop
had nothing to iterate, so the row-shape assertion never executed. The driver it
clears is the shipped fixture; only the clearance — the report's subject — is built.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.driver_clearance_register.driver_clearance_register import execute

test_dependencies = ["Salis Driver"]

DRIVER_NAME = "_Test Driver"

_EXPECTED_FIELDS = [
    "name",
    "driver",
    "clearance_reason",
    "status",
    "outstanding_fuel_exceptions",
    "outstanding_recoveries",
]


class TestDriverClearanceRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.clearance = frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": self.driver,
                "clearance_reason": "End of Assignment",
                "status": "Open",
                "vehicle_returned": 1,
                "fuel_chip_returned": 1,
                "custody_returned": 1,
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
        self.assertTrue(data, "The seeded clearance must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_seeded_clearance_reports_its_driver_and_zero_outstanding_counters(self):
        _columns, data, *_rest = execute({"driver": self.driver})
        seeded = [row for row in data if row["name"] == self.clearance]
        self.assertEqual(len(seeded), 1, "The seeded clearance must contribute one row.")
        self.assertEqual(seeded[0]["driver"], self.driver)
        self.assertEqual(seeded[0]["clearance_reason"], "End of Assignment")
        self.assertEqual(seeded[0]["status"], "Open")
        # Server-derived on validate; the fixture driver has no open cases against them.
        self.assertEqual(seeded[0]["outstanding_fuel_exceptions"], 0)
        self.assertEqual(seeded[0]["outstanding_recoveries"], 0)
