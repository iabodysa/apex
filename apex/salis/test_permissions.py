from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis import permissions


class TestMasarProjectScope(FrappeTestCase):
    def test_actual_trip_uses_direct_project_with_legacy_fallback(self):
        kind, spec = permissions.SALIS_SCOPE["Dispatch Trip"]

        self.assertEqual(kind, "trip")
        self.assertEqual(spec["own"], "trip_actor")

    def test_route_assignment_allows_its_named_supervisor(self):
        kind, spec = permissions.SALIS_SCOPE["Route Assignment"]

        self.assertEqual(kind, "column")
        self.assertEqual(spec["own"], "route_supervisor")
        self.assertEqual(spec["rule"], "route_assignment")

    @patch.object(permissions, "_allowed_projects_for", return_value=["PROJ-1"])
    @patch.object(permissions, "_is_unscoped", return_value=False)
    def test_trip_query_prefers_direct_project_and_keeps_legacy_rows(
        self, _unscoped, _allowed
    ):
        condition = permissions.project_scope_query(
            user="supervisor@example.com", doctype="Dispatch Trip"
        )

        self.assertIn("`project` in ('PROJ-1')", condition)
        self.assertIn("coalesce(`project`, '') = ''", condition)
        self.assertIn("`route_plan` in (select `name` from `tabRoute Plan`", condition)
        self.assertIn("`route_assignment` in (select `name` from `tabRoute Assignment`", condition)

    @patch.object(permissions, "_allowed_projects_for", return_value=[])
    @patch.object(permissions, "_is_unscoped", return_value=False)
    def test_assignment_query_keeps_only_named_supervisor_without_project_scope(
        self, _unscoped, _allowed
    ):
        condition = permissions.project_scope_query(
            user="supervisor@example.com", doctype="Route Assignment"
        )

        self.assertEqual(condition, "`route_supervisor` = 'supervisor@example.com'")

    @patch.object(permissions.frappe.db, "get_value")
    def test_child_document_resolves_direct_trip_project_before_legacy_plan(
        self, get_value
    ):
        get_value.return_value = frappe._dict(
            project="PROJ-NEW", route_plan="RP-OLD"
        )
        doc = frappe._dict(
            doctype="Trip Start Log", dispatch_trip="DT-1", route_plan="RP-OLD"
        )

        self.assertEqual(permissions._doc_project(doc), "PROJ-NEW")
        get_value.assert_called_once_with(
            "Dispatch Trip", "DT-1", ["project", "route_plan"], as_dict=True
        )

    @patch.object(permissions, "_allowed_projects_for", return_value=[])
    @patch.object(permissions, "_is_unscoped", return_value=False)
    def test_named_supervisor_can_open_their_assignment(self, _unscoped, _allowed):
        doc = frappe._dict(
            doctype="Route Assignment",
            route_supervisor="supervisor@example.com",
            project="PROJ-OTHER",
        )

        self.assertIsNone(
            permissions.project_scoped_has_permission(
                doc, "read", user="supervisor@example.com"
            )
        )

    @patch.object(permissions, "_allowed_projects_for", return_value=[])
    @patch.object(permissions, "_is_unscoped", return_value=False)
    def test_other_supervisor_cannot_open_assignment_outside_scope(
        self, _unscoped, _allowed
    ):
        doc = frappe._dict(
            doctype="Route Assignment",
            route_supervisor="other@example.com",
            project="PROJ-OTHER",
        )

        self.assertFalse(
            permissions.project_scoped_has_permission(
                doc, "read", user="supervisor@example.com"
            )
        )

    @patch.object(permissions, "get_driver_for_session_user", return_value=None)
    @patch.object(
        permissions.frappe.db,
        "get_value",
        return_value="supervisor@example.com",
    )
    @patch.object(permissions, "_is_unscoped", return_value=False)
    def test_named_supervisor_can_open_trip_from_their_assignment(
        self, _unscoped, get_value, _driver
    ):
        trip = frappe._dict(
            doctype="Dispatch Trip",
            route_assignment="RA-1",
            route_plan=None,
            driver=None,
            project="PROJ-OTHER",
        )

        self.assertIsNone(
            permissions.project_scoped_has_permission(
                trip, "read", user="supervisor@example.com"
            )
        )
        get_value.assert_called_once_with(
            "Route Assignment", "RA-1", "route_supervisor"
        )
