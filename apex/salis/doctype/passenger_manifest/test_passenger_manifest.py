# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Passenger Manifest duplicate-passenger guard (T-709).

A duplicate employee row inflates passenger_count and the seat headcount, so a
repeated employee is rejected; distinct rows pass and passenger_count mirrors the
row total. Empty-employee rows are ignored by the guard.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = ["Employee", "Salis Vehicle", "Salis Driver", "Route Plan", "Dispatch Trip", "Payment Gateway"]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


def _manifest(employees):
    # Unsaved controller; run validate() directly to exercise the guard + count
    # recompute without pulling the dispatch/vehicle link graph.
    doc = frappe.get_doc({"doctype": "Passenger Manifest"})
    for emp in employees:
        doc.append("passengers", {"employee": emp})
    return doc


class TestPassengerManifestDuplicates(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.emp1 = self._employee()
        self.emp2 = self._employee()

    def _employee(self):
        emp = frappe.get_doc(
            {"doctype": "Employee", "first_name": "PM-" + _h(), "naming_series": "HR-EMP-"}
        )
        emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(frappe.delete_doc, "Employee", emp.name, force=True, ignore_permissions=True)
        return emp.name

    def test_duplicate_employee_is_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            _manifest([self.emp1, self.emp1]).validate()

    def test_distinct_employees_pass_and_count_matches(self):
        # Non-vacuous: two distinct passengers validate and passenger_count == 2.
        doc = _manifest([self.emp1, self.emp2])
        doc.validate()
        self.assertEqual(doc.passenger_count, 2)

    def test_empty_employee_rows_are_ignored_by_guard(self):
        # Blank-employee rows don't collide; the guard skips them.
        doc = _manifest([self.emp1, None, None])
        doc.validate()
        self.assertEqual(doc.passenger_count, 3)
