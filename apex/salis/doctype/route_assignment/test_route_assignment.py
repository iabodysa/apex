from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


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
