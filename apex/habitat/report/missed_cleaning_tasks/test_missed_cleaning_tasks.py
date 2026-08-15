# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Missed Cleaning Tasks report execute().

Asserts the column contract and that execute() runs end-to-end (default 30-day
window + building scope for Administrator) returning a data list whose rows
carry every declared field. Requires a live site (queries Cleaning Log).

The row test seeds one missed and one rework Cleaning Log inside the default
window: on an empty test database the per-row loop had nothing to iterate, so the
row-shape assertion never executed and the two-query union went unproven."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.report.missed_cleaning_tasks.missed_cleaning_tasks import execute

_EXPECTED_FIELDS = [
    "name",
    "cleaning_date",
    "building",
    "cleaner_type",
    "cleaner",
    "issue",
    "missed_reason",
    "supervisor_approved",
    "scheduled_task_instance",
    "days_since",
]


class TestMissedCleaningTasks(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12).upper()
        # A dedicated building per test: Cleaning Log carries a DB-level unique
        # constraint on (building, cleaning_date, docstatus).
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"MCT Bldg {tag}",
                "status": "Active",
                "total_capacity": 10,
            }
        ).insert(ignore_permissions=True).name

        self.missed = self._log(
            add_days(today(), -3),
            missed_cleaning=1,
            missed_reason="Cleaner absent without cover.",
        )
        self.rework = self._log(add_days(today(), -2), rework_required=1)

    def _log(self, cleaning_date, **flags):
        return frappe.get_doc(
            {
                "doctype": "Cleaning Log",
                "building": self.building,
                "cleaning_date": cleaning_date,
                "cleaner_type": "Internal Employee",
                "cleaner_name": "MCT Cleaner",
                **flags,
            }
        ).insert(ignore_permissions=True).name

    def test_columns_contract(self):
        columns, data, *_rest = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data, *_rest = execute({})
        self.assertTrue(data, "The seeded cleaning logs must reach the report.")

        checked = 0
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
            checked += 1
        self.assertEqual(
            checked, len(data), "The per-row assertions must run for every row."
        )

    def test_missed_and_rework_logs_are_both_reported_with_their_issue_label(self):
        _columns, data, *_rest = execute({"building": self.building})
        by_name = {row["name"]: row for row in data}

        self.assertIn(self.missed, by_name, "A missed log must appear in the report.")
        self.assertIn(self.rework, by_name, "A rework log must appear in the report.")
        self.assertEqual(by_name[self.missed]["issue"], "Missed")
        self.assertEqual(by_name[self.rework]["issue"], "Rework Required")
        self.assertEqual(by_name[self.missed]["days_since"], 3)
        self.assertEqual(by_name[self.missed]["cleaner"], "MCT Cleaner")
