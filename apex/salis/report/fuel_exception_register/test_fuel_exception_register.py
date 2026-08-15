# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Exception Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field. Requires a live site (queries Fuel
Exception Case).

The row test seeds an open case: on an empty test database the per-row loop had
nothing to iterate, so the row-shape assertion never executed. The vehicle, the
driver and the project the case names are read rather than built.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.fuel_exception_register.fuel_exception_register import execute

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent —
# its autoname mints a new name while project_name carries a unique index, so a second
# build attempt collides instead of being skipped. The case only needs a project id, so
# the one already on the site is read rather than rebuilt.
test_dependencies = ["Salis Vehicle", "Salis Driver"]

PLATE = "_T ABC 1001"
DRIVER_NAME = "_Test Driver"

_EXPECTED_FIELDS = [
    "name",
    "exception_type",
    "vehicle",
    "driver",
    "project",
    "status",
    "amount_recovered",
    "reported_by",
    "closed_by",
]


class TestFuelExceptionRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.case = frappe.get_doc(
            {
                "doctype": "Fuel Exception Case",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "project": self.project,
                "exception_type": "Over-Consumption",
                "description": "Litres claimed exceed the ledger for the period.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
        self.assertTrue(data, "The seeded exception case must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_seeded_case_reports_its_subject_and_the_server_stamped_raiser(self):
        _columns, data, *_rest = execute({"exception_type": "Over-Consumption"})
        seeded = [row for row in data if row["name"] == self.case]
        self.assertEqual(len(seeded), 1, "The seeded case must contribute one row.")
        self.assertEqual(seeded[0]["vehicle"], self.vehicle)
        self.assertEqual(seeded[0]["driver"], self.driver)
        self.assertEqual(seeded[0]["project"], self.project)
        self.assertEqual(seeded[0]["status"], "Open")
        # reported_by is stamped server-side from the session, never sent by the client.
        self.assertEqual(seeded[0]["reported_by"], "Administrator")
        self.assertFalse(seeded[0]["closed_by"], "An open case has no closer yet.")
