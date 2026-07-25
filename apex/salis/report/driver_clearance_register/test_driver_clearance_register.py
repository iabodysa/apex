# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Driver Clearance Register report execute().

Asserts the column contract and that execute() runs end-to-end (project scope
unrestricted for Administrator) returning a data list whose rows carry every
declared field. Requires a live site (queries Driver Clearance)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.driver_clearance_register.driver_clearance_register import execute

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

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
