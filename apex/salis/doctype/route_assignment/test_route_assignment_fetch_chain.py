# Copyright (c) 2026, AFMCO and contributors
"""The declarative half of Route Assignment: the fetch chain off the linked Work Shift.

Three fields carry ``fetch_from`` on ``work_shift`` — ``shift_name``,
``shift_start_time`` and ``shift_end_time`` — and a fetch only runs on a real write, so
these cases insert rather than call ``validate``. ``project`` is deliberately NOT among
them: it is its own mandatory Link on the assignment, because a shift is a time of day
and does not belong to one project. The sibling ``test_route_assignment.py`` grades that
same boundary from the controller's side.

Only ``shift_name`` is asserted. The two Time fetches do not currently copy the shift's
times, so there is no correct value to pin here yet.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRouteAssignmentFetchChain(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = frappe.get_doc(
            {
                "doctype": "Project",
                "project_name": f"RA Fetch Project {frappe.generate_hash(length=12)}",
            }
        ).insert(ignore_permissions=True).name
        cls.work_shift = frappe.get_doc(
            {
                "doctype": "Work Shift",
                "shift_name": "RA Fetch Shift",
                "start_time": "06:00:00",
                "end_time": "14:00:00",
                "applicable_days": [{"day_of_week": "Monday"}],
            }
        ).insert(ignore_permissions=True).name
        cls.route_template = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": f"RA Fetch Template {frappe.generate_hash(length=12)}",
                "route_type": "Pickup",
                "stops": [{"stop_name": "Housing"}],
            }
        ).insert(ignore_permissions=True).name

    def _assignment(self, **overrides):
        values = {
            "doctype": "Route Assignment",
            "route_template": self.route_template,
            "work_shift": self.work_shift,
            "project": self.project,
            "starts_on": frappe.utils.today(),
        }
        values.update(overrides)
        return frappe.get_doc(values)

    def test_the_shift_identity_is_fetched_onto_the_assignment(self):
        shift_name = frappe.db.get_value("Work Shift", self.work_shift, "shift_name")

        assignment = self._assignment()
        assignment.insert(ignore_permissions=True)

        self.assertEqual(
            frappe.db.get_value("Route Assignment", assignment.name, "shift_name"), shift_name
        )

    def test_the_project_is_the_assignments_own_and_is_not_fetched_from_the_shift(self):
        """Work Shift carries no project field at all, so a fetch could not exist —
        this pins that the assignment keeps the project it was given."""
        self.assertIsNone(frappe.get_meta("Work Shift").get_field("project"))
        assignment = self._assignment()
        assignment.insert(ignore_permissions=True)
        self.assertEqual(assignment.project, self.project)

    def test_an_assignment_with_no_shift_is_refused(self):
        with self.assertRaises(frappe.exceptions.MandatoryError):
            self._assignment(work_shift=None).insert(ignore_permissions=True)
