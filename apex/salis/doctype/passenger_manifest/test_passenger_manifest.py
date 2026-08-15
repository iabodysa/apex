# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Passenger Manifest duplicate-passenger guard (T-709).

A duplicate employee row inflates passenger_count and the seat headcount, so a
repeated employee is rejected; distinct rows pass and passenger_count mirrors the
row total. Empty-employee rows are ignored by the guard.

The two passengers are the shipped Employee fixtures; naming the dependency is what
replaced the ``test_ignore`` block that used to prune the walk behind their construction.
Nothing here is inserted — the guard is exercised on an unsaved document.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Employee"]

WORKER = "_Test Employee"
OTHER_WORKER = "_Test Employee 1"


def _manifest(employees):
    doc = frappe.get_doc({"doctype": "Passenger Manifest"})
    for emp in employees:
        doc.append("passengers", {"employee": emp})
    return doc


class TestPassengerManifestDuplicates(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.emp1 = frappe.db.get_value("Employee", {"first_name": WORKER})
        self.emp2 = frappe.db.get_value("Employee", {"first_name": OTHER_WORKER})

    def test_duplicate_employee_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _manifest([self.emp1, self.emp1]).validate()

    def test_distinct_employees_pass_and_count_matches(self):
        doc = _manifest([self.emp1, self.emp2])
        doc.validate()
        self.assertEqual(doc.passenger_count, 2)

    def test_empty_employee_rows_are_ignored_by_guard(self):
        doc = _manifest([self.emp1, None, None])
        doc.validate()
        self.assertEqual(doc.passenger_count, 3)
