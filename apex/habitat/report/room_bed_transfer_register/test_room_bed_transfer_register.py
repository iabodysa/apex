# Copyright (c) 2026, afmcoltd

"""Tests for the Room Bed Transfer Register report.

Pins the report's mechanical contract: every column's fieldname must be a key
on each row ``execute()`` returns, and the building scope guard — resolved
through the transfer's Housing Assignment — must confine a scoped caller
holding no Building User Permission to zero rows while still handing back
the column definitions.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.room_bed_transfer_register.room_bed_transfer_register import execute
from apex.tests._helpers import _user, as_user
from apex.tests.factories import (
    default_company,
    make_assignment,
    make_bed,
    make_building,
    make_project,
    make_worker_employee,
)


class TestRoomBedTransferRegister(FrappeTestCase):
    """Exercises the register's column/row contract and its building scope guard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.employee = make_worker_employee("A564 RBTR Employee")
        cls.building = make_building("A564 RBTR Building", company=default_company()).name
        cls.project = make_project("A564 RBTR Project")
        cls.assignment = make_assignment(
            cls.employee,
            cls.building,
            cls.project,
            room_number="A564-RBTR-R1",
            bed_code="A564-RBTR-R1-B1",
        )
        cls.to_bed = make_bed("A564-RBTR-R1", bed_code="A564-RBTR-R1-B2").name
        transfer = frappe.get_doc(
            {
                "doctype": "Room Bed Transfer",
                "assignment": cls.assignment,
                "to_room": "A564-RBTR-R1",
                "to_bed": cls.to_bed,
                "transfer_date": frappe.utils.today(),
            }
        )
        transfer.insert(ignore_permissions=True)
        transfer.submit()
        cls.transfer = transfer.name

    def setUp(self):
        """Runs every case as Administrator, regardless of what the previous case switched to."""
        frappe.set_user("Administrator")

    def tearDown(self):
        """Restores the Administrator session after a case that switched users."""
        frappe.set_user("Administrator")

    def test_columns_and_row_fieldnames_agree(self):
        """Every column's fieldname must be a key on each row execute() returns."""
        columns, rows, _chart, _report_summary, _summary = execute({"building": self.building})

        self.assertTrue(rows, "the fixture transfer must be visible to an unscoped caller")
        fieldnames = {column["fieldname"] for column in columns}
        for row in rows:
            missing = fieldnames - set(row.keys())
            self.assertEqual(missing, set(), f"row is missing declared column fieldnames: {missing}")

    def test_out_of_scope_caller_gets_columns_and_no_rows(self):
        """A building-scoped caller holding no Building User Permission sees zero rows."""
        outsider = _user("a564-rbtr-outsider@test.local", "Resident Supervisor")
        with as_user(outsider):
            columns, rows, _chart, _report_summary, summary = execute({"building": self.building})

        self.assertTrue(columns, "columns must still be returned to an out-of-scope caller")
        self.assertEqual(rows, [])
        self.assertEqual(summary[0]["value"], 0)
