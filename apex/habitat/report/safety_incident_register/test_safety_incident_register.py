# Copyright (c) 2026, afmcoltd

"""Tests for the Safety Incident Register report.

Pins the report's mechanical contract: every column's fieldname must be a
key on each row ``execute()`` returns, and the building scope guard must
confine a scoped caller holding no Building User Permission to zero rows
while still handing back the column definitions.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.safety_incident_register.safety_incident_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import default_company, make_building


def _submitted_incident(building):
    """Insert and submit a High-severity Safety Incident on ``building``; return it."""
    doc = frappe.get_doc(
        {
            "doctype": "Safety Incident",
            "incident_datetime": frappe.utils.now_datetime(),
            "building": building,
            "severity": "High",
            "description": "A564 fixture incident.",
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


class TestSafetyIncidentRegister(FrappeTestCase):
    """Exercises the register's column/row contract and its building scope guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.building = make_building("A564 SIR Building", company=default_company()).name
        cls.incident = _submitted_incident(cls.building)

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_columns_and_row_fieldnames_agree(self):
        """Every column's fieldname must be a key on each row execute() returns."""
        columns, rows, _chart, _report_summary, _summary = execute({"building": self.building})

        self.assertTrue(rows, "the fixture incident must be visible to an unscoped caller")
        fieldnames = {column["fieldname"] for column in columns}
        for row in rows:
            missing = fieldnames - set(row.keys())
            self.assertEqual(missing, set(), f"row is missing declared column fieldnames: {missing}")

    def test_out_of_scope_caller_gets_columns_and_no_rows(self):
        """A building-scoped caller holding no Building User Permission sees zero rows."""
        outsider = _user("a564-sir-outsider@test.local", "Resident Supervisor")
        with as_user(outsider):
            columns, rows, _chart, _report_summary, summary = execute({"building": self.building})

        self.assertTrue(columns, "columns must still be returned to an out-of-scope caller")
        self.assertEqual(rows, [])
        self.assertEqual(summary[0]["value"], 0)
