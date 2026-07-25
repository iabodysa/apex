# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Exception Register report execute().

Asserts the column contract and that execute() runs end-to-end returning a data
list whose rows carry every declared field. Requires a live site (queries Fuel
Exception Case).

The row test seeds an open case: on an empty test database the per-row loop had
nothing to iterate, so the row-shape assertion never executed."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.fuel_exception_register.fuel_exception_register import execute

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
        tag = frappe.generate_hash(length=12).upper()

        self.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"FER Project {tag}"}
        ).insert(ignore_permissions=True).name
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"FER-{tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        self.driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": f"FER Driver {tag}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
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
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
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
        _columns, data = execute({"exception_type": "Over-Consumption"})
        seeded = [row for row in data if row["name"] == self.case]
        self.assertEqual(len(seeded), 1, "The seeded case must contribute one row.")
        self.assertEqual(seeded[0]["vehicle"], self.vehicle)
        self.assertEqual(seeded[0]["driver"], self.driver)
        self.assertEqual(seeded[0]["project"], self.project)
        self.assertEqual(seeded[0]["status"], "Open")
        # reported_by is stamped server-side from the session, never sent by the client.
        self.assertEqual(seeded[0]["reported_by"], "Administrator")
        self.assertFalse(seeded[0]["closed_by"], "An open case has no closer yet.")
