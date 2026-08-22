from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
import unittest
from unittest import mock
from apex.salis.doctype.route_assignment.route_assignment import RouteAssignment
from apex.tests._helpers import _user

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

ASSIGNMENT = "RA-1"
def _cancel(generated=("DT-1", "DT-2")):
    """Run ``on_cancel`` on a stand-in and report what it asked frappe to do."""
    doc = mock.Mock(spec=RouteAssignment)
    doc.name = ASSIGNMENT

    mock_frappe = mock.MagicMock()
    mock_frappe.get_all.return_value = list(generated)

    with mock.patch(
        "apex.salis.doctype.route_assignment.route_assignment.frappe", mock_frappe
    ):
        RouteAssignment.on_cancel(doc)
    return doc, mock_frappe
class TestRouteAssignmentCancel(unittest.TestCase):
    def test_generated_draft_trips_are_deleted(self):
        _doc, mock_frappe = _cancel()
        deleted = [call.args[1] for call in mock_frappe.delete_doc.call_args_list]
        self.assertEqual(["DT-1", "DT-2"], deleted)

    def test_only_this_assignments_unrun_drafts_are_selected(self):
        _doc, mock_frappe = _cancel()
        filters = mock_frappe.get_all.call_args.kwargs["filters"]
        self.assertEqual(ASSIGNMENT, filters["route_assignment"])
        self.assertEqual(0, filters["docstatus"])
        self.assertEqual("Planned", filters["status"])

    def test_the_delete_carries_no_permission_bypass(self):
        """Fleet Manager owns both the Cancel transition and delete on Dispatch Trip,
        so the acting user's own rights carry this — there is no need to bypass."""
        _doc, mock_frappe = _cancel()
        for call in mock_frappe.delete_doc.call_args_list:
            self.assertNotIn("ignore_permissions", call.kwargs)
            self.assertNotIn("force", call.kwargs)

    def test_the_generation_watermark_is_cleared(self):
        doc, _mock_frappe = _cancel()
        doc.db_set.assert_called_once_with("generated_through", None)

    def test_nothing_generated_still_clears_the_watermark(self):
        doc, mock_frappe = _cancel(generated=())
        mock_frappe.delete_doc.assert_not_called()
        doc.db_set.assert_called_once_with("generated_through", None)
if __name__ == "__main__":
    unittest.main()

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

class TestRouteAssignmentCancelPermission(FrappeTestCase):
    def test_fleet_manager_holds_cancel_the_workflow_offers_him(self):
        frappe.set_user("Administrator")
        manager = _user("ra_cancel_fm@example.com", "Fleet Manager")
        self.assertTrue(
            frappe.has_permission("Route Assignment", "cancel", user=manager),
            "the workflow's own Cancel transition (Approved -> Cancelled) is offered "
            "only to Fleet Manager, so that role must hold cancel or the button "
            "always raises",
        )
