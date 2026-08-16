# Copyright (c) 2026, afmcoltd
"""Idle Resident Detection: an active resident whose project has ended is a candidate, one whose
project is still open is not, and a report already open against the candidate is joined in.

The building, its rooms, its beds and the employees all come from ``test_records.json``. The one
record still built here is the ENDED project — that is the report's whole discriminator, so
building it is asserting, not arranging. The previous form of this file stood up a Company, a
Building, two Projects, two Rooms, two Beds, two Employees and two Assignments in ``setUp``, per
test method.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.idle_resident_detection.idle_resident_detection import execute

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped. The open project is read; the ended one is built here.
test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"


class TestIdleResidentDetection(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the
        # assignments one case houses in the fixture beds would still be holding them when the
        # next case tries. A savepoint is the framework's own way to hand the beds back.
        frappe.db.savepoint("apex_idle_resident_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_idle_resident_case")

        self.cost_center = frappe.db.get_value("Building", BUILDING, "default_cost_center")
        self.open_project = frappe.db.get_value("Project", {"project_name": "_Test Project"})

        ended = frappe.get_doc({
            "doctype": "Project",
            "project_name": "_T Ended " + frappe.generate_hash(length=12),
        }).insert(ignore_permissions=True).name
        frappe.db.set_value("Project", ended, "status", "Completed")
        self.ended_project = ended

        self.on_open = self._assignment(self.open_project, "_Test Employee", "_T-101", "_T-101-A")
        self.on_ended = self._assignment(self.ended_project, "_Test Employee 1", "_T-102", "_T-102-A")

    def _assignment(self, project, employee_first_name, room, bed):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": frappe.db.get_value("Employee", {"first_name": employee_first_name}),
            "project": project,
            "building": BUILDING,
            "room": room,
            "bed": bed,
            "cost_center": self.cost_center,
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        doc.submit()
        return doc.name

    def _by_assignment(self, data):
        return {row["name"]: row for row in data}

    def test_only_a_resident_on_an_ended_project_is_a_candidate(self):
        _columns, data, *_rest = execute({"building": BUILDING})
        rows = self._by_assignment(data)

        self.assertIn(self.on_ended, rows, "a completed-project resident must be a candidate")
        self.assertNotIn(self.on_open, rows, "an open-project resident must be excluded")
        self.assertEqual(rows[self.on_ended]["project_status"], "Completed")
        self.assertIsNone(rows[self.on_ended]["existing_idle_report"])

    def test_an_open_idle_report_is_joined_in_and_hidden_by_only_unlogged(self):
        report = frappe.get_doc({
            "doctype": "Idle Resident Report",
            "naming_series": "IDLE-.YYYY.-.####",
            "party_type": "Employee",
            "party": frappe.db.get_value("Housing Assignment", self.on_ended, "employee"),
            "employee": frappe.db.get_value("Housing Assignment", self.on_ended, "employee"),
            "assignment": self.on_ended,
            "building": BUILDING,
            "reason_category": "Other",
            "responsible_department": "Operations",
            "status": "Open",
        }).insert(ignore_permissions=True).name

        _columns, data, *_rest = execute({"building": BUILDING})
        row = self._by_assignment(data)[self.on_ended]
        self.assertEqual(row["existing_idle_report"], report)
        self.assertEqual(row["idle_report_status"], "Open")

        _columns, unlogged, *_rest = execute({"building": BUILDING, "only_unlogged": 1})
        self.assertNotIn(self.on_ended, self._by_assignment(unlogged))

    def test_the_project_status_filter_narrows_to_one_status(self):
        _columns, data, *_rest = execute({"building": BUILDING, "project_status": "Cancelled"})

        self.assertNotIn(self.on_ended, self._by_assignment(data))
