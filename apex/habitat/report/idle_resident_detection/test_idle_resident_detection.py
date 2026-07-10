# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Idle Resident Detection report.

Proves execute() surfaces only active residents whose linked Project has ended
(Completed/Cancelled) — an Open-project resident is excluded, an ended-project
resident is a candidate, project_status is reported, an existing open Idle
Resident Report is joined in, and only_unlogged hides already-logged candidates.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.idle_resident_detection.idle_resident_detection import execute


class TestIdleResidentDetection(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = frappe.generate_hash(length=12).upper()

        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "IRC Co " + tag,
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) \
            or frappe.db.get_value("Cost Center", {"is_group": 0})

        self.building = frappe.get_doc({
            "doctype": "Building", "building_name": f"IRC Bldg {tag}",
            "status": "Active", "total_capacity": 10, "company": company,
            "default_cost_center": self.cc,
        }).insert(ignore_permissions=True).name
        self.company = company

        # Two ended-work projects and one live one.
        self.project_open = self._project(f"IRC Open {tag}", "Open")
        self.project_done = self._project(f"IRC Done {tag}", "Completed")

        # Active resident on the live project — NOT idle.
        self.asg_open = self._assignment(self.project_open, tag, "OPN")
        # Active resident on the completed project — idle candidate.
        self.asg_done = self._assignment(self.project_done, tag, "DON")

    def _project(self, name, status):
        proj = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
            ignore_permissions=True
        ).name
        frappe.db.set_value("Project", proj, "status", status)
        return proj

    def _assignment(self, project, tag, slot):
        room = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####",
            "building": self.building, "room_number": f"R{slot}{tag}", "bed_capacity": 4,
            "readiness_status": "Ready",
        }).insert(ignore_permissions=True).name
        bed = frappe.get_doc({
            "doctype": "Bed", "naming_series": "BED-.####", "room": room,
            "building": self.building, "bed_code": f"B{slot}{tag}", "status": "Available",
        }).insert(ignore_permissions=True).name
        emp = frappe.get_doc({
            "doctype": "Employee", "first_name": f"E{slot} {tag}", "company": self.company,
            "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        asg = frappe.get_doc({
            "doctype": "Housing Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": emp, "project": project, "building": self.building, "room": room,
            "bed": bed, "cost_center": self.cc, "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        asg.submit()
        return asg.name

    def _rows_by_assignment(self, data):
        return {row["name"]: row for row in data}

    def test_only_ended_project_residents_are_candidates(self):
        _columns, data = execute({"building": self.building})
        by_asg = self._rows_by_assignment(data)

        self.assertIn(self.asg_done, by_asg, "completed-project resident must be a candidate")
        self.assertNotIn(self.asg_open, by_asg, "open-project resident must be excluded")
        self.assertEqual(by_asg[self.asg_done]["project_status"], "Completed")
        self.assertIsNone(by_asg[self.asg_done]["existing_idle_report"])

    def test_existing_open_idle_report_is_joined(self):
        emp = frappe.db.get_value("Housing Assignment", self.asg_done, "employee")
        report = frappe.get_doc({
            "doctype": "Idle Resident Report", "naming_series": "IDLE-.YYYY.-.####",
            "party_type": "Employee", "party": emp, "employee": emp,
            "assignment": self.asg_done, "building": self.building,
            "reason_category": "Other", "responsible_department": "Operations",
            "status": "Open",
        }).insert(ignore_permissions=True).name

        _columns, data = execute({"building": self.building})
        row = self._rows_by_assignment(data)[self.asg_done]
        self.assertEqual(row["existing_idle_report"], report)
        self.assertEqual(row["idle_report_status"], "Open")

        # only_unlogged must now hide this already-logged candidate.
        _columns, data2 = execute({"building": self.building, "only_unlogged": 1})
        self.assertNotIn(self.asg_done, self._rows_by_assignment(data2))

    def test_project_status_filter_narrows_to_one_status(self):
        # Filtering to Cancelled excludes the Completed-project candidate.
        _columns, data = execute({"building": self.building, "project_status": "Cancelled"})
        self.assertNotIn(self.asg_done, self._rows_by_assignment(data))
