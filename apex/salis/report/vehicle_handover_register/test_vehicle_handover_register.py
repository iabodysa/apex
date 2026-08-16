# Copyright (c) 2026, afmcoltd

"""Tests for the Vehicle Handover Register report.

Pins the report's mechanical contract: every column's fieldname must be a key
on each row ``execute()`` returns, and the project scope guard must confine a
scoped caller holding no Project User Permission to zero rows while still
handing back the column definitions.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.report.vehicle_handover_register.vehicle_handover_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_project, make_vehicle


def _driver(full_name):
    """Get-or-create an Active Salis Driver carrying no Employee link; return its name."""
    existing = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if existing:
        return existing
    return (
        frappe.get_doc({"doctype": "Salis Driver", "full_name": full_name, "status": "Active"})
        .insert(ignore_permissions=True)
        .name
    )


def _submitted_handover(vehicle, from_driver, to_driver, odometer):
    """Insert and submit a Transfer-direction Vehicle Handover; return the document."""
    doc = frappe.get_doc(
        {
            "doctype": "Vehicle Handover",
            "vehicle": vehicle,
            "direction": "Transfer",
            "from_driver": from_driver,
            "to_driver": to_driver,
            "handover_date": frappe.utils.today(),
            "odometer_reading": odometer,
            "signed_evidence": "/files/a564-vhr-evidence.png",
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc


class TestVehicleHandoverRegister(FrappeTestCase):
    """Exercises the register's column/row contract and its project scope guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = make_project("A564 VHR Project")
        cls.vehicle = make_vehicle("A564-VHR-1", project=cls.project)
        cls.driver_a = _driver("A564 VHR Driver A")
        cls.driver_b = _driver("A564 VHR Driver B")
        cls.handover = _submitted_handover(cls.vehicle, cls.driver_a, cls.driver_b, 100)

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_columns_and_row_fieldnames_agree(self):
        """Every column's fieldname must be a key on each row execute() returns."""
        columns, rows, _chart, _report_summary, _summary = execute({"vehicle": self.vehicle})

        self.assertTrue(rows, "the fixture handover must be visible to an unscoped caller")
        fieldnames = {column["fieldname"] for column in columns}
        for row in rows:
            missing = fieldnames - set(row.keys())
            self.assertEqual(missing, set(), f"row is missing declared column fieldnames: {missing}")

    def test_out_of_scope_caller_gets_columns_and_no_rows(self):
        """A project-scoped caller holding no Project User Permission sees zero rows."""
        outsider = _user("a564-vhr-outsider@test.local", "Fleet Supervisor")
        with as_user(outsider):
            columns, rows, _chart, _report_summary, summary = execute({"vehicle": self.vehicle})

        self.assertTrue(columns, "columns must still be returned to an out-of-scope caller")
        self.assertEqual(rows, [])
        self.assertEqual(summary[0]["value"], 0)
