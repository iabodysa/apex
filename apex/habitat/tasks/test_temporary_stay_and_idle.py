# Copyright (c) 2026, afmcoltd
"""Temporary-stay validation on Housing Assignment, and the Idle Resident Report status flow: a
temporary stay must name the date it ends, an idle report must not be resolved without notes or
duplicated while one is open, it routes a ToDo to the responsible department, and the ageing job
accrues the days.

The building, its room, its bed, the employee and the project all come from ``test_records.json``.
The two users are still built here, because who receives the alert and who receives the routed ToDo
IS what those two cases assert. The previous form of this file built a Company, a Site, a Building,
an Employee and a Project in ``setUp``, per test method, for seven test methods.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.
test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"
ROOM = "_T-101"
BED = "_T-101-A"


class TestTemporaryStayAndIdle(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the open idle
        # report one case files would still be open when the duplicate case runs, and the
        # supervisor one case pins on the building would still be pinned. A savepoint hands the
        # building and the report back.
        frappe.db.savepoint("apex_temporary_stay_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_temporary_stay_case")

        self.cost_center = frappe.db.get_value("Building", BUILDING, "default_cost_center")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})

    def _user(self, prefix, roles=()):
        email = "{0}{1}@test.com".format(prefix, frappe.generate_hash(length=12)).lower()
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": prefix.title(),
            "send_welcome_email": 0, "roles": [{"role": role} for role in roles],
        }).insert(ignore_permissions=True).name

    def _assignment(self, stay_type, expected_checkout_date=None):
        return frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": self.employee,
            "project": self.project,
            "building": BUILDING,
            "cost_center": self.cost_center,
            "check_in_date": "2026-05-01",
            "stay_type": stay_type,
            "expected_checkout_date": expected_checkout_date,
        })

    def _idle_report(self, **overrides):
        payload = {
            "doctype": "Idle Resident Report",
            "naming_series": "IDLE-.YYYY.-.####",
            "employee": self.employee,
            "building": BUILDING,
            "reason_category": "New Hire",
            "responsible_department": "Operations",
            "status": "Open",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_the_expected_checkout_alert_is_addressed_to_the_buildings_supervisor(self):
        supervisor = self._user("sup")
        frappe.db.set_value("Building", BUILDING, "responsible_supervisor", supervisor)

        assignment = self._assignment("Permanent")
        assignment.room = ROOM
        assignment.bed = BED
        assignment.insert(ignore_permissions=True)
        self.assertEqual(assignment.responsible_supervisor, supervisor)

        notification = frappe.get_doc("Notification", "Habitat - Expected Checkout Approaching")
        context = {"doc": assignment, "alert": notification, "comments": None}
        recipients, _cc, _bcc = notification.get_list_of_recipients(assignment, context)

        self.assertIn(supervisor, recipients, "the building's responsible_supervisor must be a recipient")

    def test_a_temporary_stay_without_the_date_it_ends_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary").insert(ignore_permissions=True)

    def test_a_temporary_stay_ending_before_it_starts_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary", "2026-04-20").insert(ignore_permissions=True)

    def test_an_idle_report_cannot_be_resolved_without_notes(self):
        report = self._idle_report().insert(ignore_permissions=True)
        report.status = "Resolved"

        with self.assertRaises(frappe.ValidationError):
            report.save(ignore_permissions=True)

    def test_a_second_open_idle_report_for_the_same_resident_is_refused(self):
        self._idle_report().insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            self._idle_report().insert(ignore_permissions=True)

    def test_a_new_idle_report_routes_a_todo_to_the_responsible_department(self):
        manager = self._user("mgr", roles=["Accommodation Manager"])
        report = self._idle_report(responsible_department="Operations").insert(ignore_permissions=True)

        todos = frappe.get_all("ToDo", filters={
            "reference_type": "Idle Resident Report",
            "reference_name": report.name,
            "allocated_to": manager,
            "status": "Open",
        })

        self.assertEqual(len(todos), 1, "an Operations role holder must get a routed ToDo")

    def test_the_ageing_job_accrues_the_days_a_report_has_been_open(self):
        from apex.habitat.tasks import idle_resident_aging

        report = self._idle_report(reported_on=add_days(today(), -7)).insert(ignore_permissions=True)

        idle_resident_aging()

        report.reload()
        self.assertEqual(report.days_idle, 7)
        self.assertEqual(report.estimated_cost_bleed, 0)
