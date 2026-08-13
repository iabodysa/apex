from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWorkShiftContract(FrappeTestCase):
    def _shift(self, *, start_time="20:00:00", end_time="05:00:00", days=None):
        return frappe.get_doc(
            {
                "doctype": "Work Shift",
                "shift_name": "Night",
                "start_time": start_time,
                "end_time": end_time,
                "applicable_days": days or [],
            }
        )

    def test_overnight_shift_is_valid_and_duplicate_days_are_removed(self):
        shift = self._shift(
            days=[
                {"day_of_week": "Monday"},
                {"day_of_week": "Monday"},
                {"day_of_week": "Tuesday"},
            ]
        )

        shift.validate()

        self.assertEqual(
            [row.day_of_week for row in shift.applicable_days],
            ["Monday", "Tuesday"],
        )

    def test_shift_requires_at_least_one_day(self):
        shift = self._shift(days=[])

        with self.assertRaises(frappe.ValidationError):
            shift.validate()

    def test_shift_rejects_equal_start_and_end_times(self):
        shift = self._shift(
            start_time="08:00:00",
            end_time="08:00:00",
            days=[{"day_of_week": "Sunday"}],
        )

        with self.assertRaises(frappe.ValidationError):
            shift.validate()


class TestRouteTemplateContract(FrappeTestCase):
    def test_template_assigns_stable_stop_keys(self):
        template = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Housing to Project",
                "route_type": "Mixed",
                "stops": [
                    {"stop_name": "Housing"},
                    {"stop_name": "Project"},
                ],
            }
        )

        template.validate()

        self.assertEqual([row.stop_key for row in template.stops], ["stop-1", "stop-2"])

    def test_template_requires_a_named_stop(self):
        template = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Empty",
                "route_type": "Mixed",
                "stops": [],
            }
        )

        with self.assertRaises(frappe.ValidationError):
            template.validate()


class TestRouteAssignmentContract(FrappeTestCase):
    @patch("apex.salis.doctype.route_assignment.route_assignment.frappe.db.get_value")
    def test_assignment_derives_display_name_without_moving_project_to_shift(self, get_value):
        labels = {
            ("Route Template", "RT-1", "template_name"): "Housing to Project",
            ("Work Shift", "WS-1", "shift_name"): "Morning",
            ("Project", "PROJ-1", "project_name"): "Airport Project",
        }
        get_value.side_effect = lambda doctype, name, fieldname: labels[
            (doctype, name, fieldname)
        ]
        assignment = frappe.get_doc(
            {
                "doctype": "Route Assignment",
                "route_template": "RT-1",
                "work_shift": "WS-1",
                "project": "PROJ-1",
                "starts_on": "2026-08-13",
            }
        )

        assignment.validate()

        self.assertEqual(
            assignment.assignment_name,
            "Housing to Project · Morning · Airport Project",
        )

    @patch("apex.salis.doctype.route_assignment.route_assignment.frappe.session")
    def test_approval_stamps_assigned_supervisor(self, session):
        session.user = "supervisor@example.com"
        assignment = frappe.get_doc(
            {
                "doctype": "Route Assignment",
                "route_template": "RT-1",
                "work_shift": "WS-1",
                "project": "PROJ-1",
                "starts_on": "2026-08-13",
                "driver": "DRV-1",
                "vehicle": "VEH-1",
                "route_supervisor": "supervisor@example.com",
                "status": "Approved",
            }
        )

        assignment.before_submit()

        self.assertEqual(assignment.approved_by, "supervisor@example.com")
        self.assertIsNotNone(assignment.approved_on)

    def test_approval_requires_complete_operational_defaults(self):
        assignment = frappe.get_doc(
            {
                "doctype": "Route Assignment",
                "route_template": "RT-1",
                "work_shift": "WS-1",
                "project": "PROJ-1",
                "starts_on": "2026-08-13",
                "status": "Approved",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            assignment.before_submit()
