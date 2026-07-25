# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Missed Cleaning Tasks report execute().

Asserts the column contract and that execute() runs end-to-end (default 30-day
window + building scope for Administrator) returning a data list whose rows
carry every declared field. Requires a live site (queries Cleaning Log)."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

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

    def test_columns_contract(self):
        columns, data = execute({})
        self.assertEqual([c["fieldname"] for c in columns], _EXPECTED_FIELDS)
        self.assertIsInstance(data, list)

    def test_rows_carry_expected_keys(self):
        _columns, data = execute({})
        for row in data:
            for key in _EXPECTED_FIELDS:
                self.assertIn(key, row)
