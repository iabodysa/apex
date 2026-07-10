# Copyright (c) 2026, AFMCO and contributors
"""Owner/assignee row-scoping for the two maintenance Script Reports.

``frappe.get_all`` forces ``ignore_permissions=True``, so the owner/assignee
row-scoping the Maintenance Request desk list gets via
``maintenance_request_query`` (permission_query_conditions) is BYPASSED inside
``maintenance_aging`` and ``open_maintenance_requests`` — a non-privileged user running
either report would otherwise see EVERY ticket's row. Each report's ``execute()``
re-applies the caller's owner/assignee scope via
``permissions.report_maintenance_request_scope`` (handed to get_all as
``or_filters``), while the privileged oversight roles in
``permissions.PRIVILEGED_ROLES`` still see everything.

Two layers of proof, mirroring ``tests/test_report_scope.py``:

* :class:`TestMaintenanceReportScopeLogic` patches the scope helper and asserts
  the ``or_filters`` each report hands to ``frappe.get_all`` (scoped ->
  owner/assignee OR-filter; oversight -> no or_filter) without any fixtures.
* :class:`TestMaintenanceReportScopeIntegration` seeds real Maintenance Requests
  spanning three owners, drives the real permission layer with
  ``frappe.set_user``, and asserts the rows a scoped vs. an oversight user
  actually gets back — including the assignee branch.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.report.maintenance_aging import maintenance_aging as R_aging
from apex_habitat.habitat.report.open_maintenance_requests import open_maintenance_requests as R_backlog
from apex_habitat.tests._helpers import _user

# [#9lw62p] A plainly non-privileged desk role (not in PRIVILEGED_ROLES).
NON_PRIVILEGED_ROLE = "Blogger"


def _last_or_filters(mock_get_all):
    """The ``or_filters`` kwarg passed to the report's (only) frappe.get_all."""
    return mock_get_all.call_args.kwargs.get("or_filters")


class TestMaintenanceReportScopeLogic(FrappeTestCase):
    """The owner/assignee or_filters each report applies, helper stubbed.

    Stubbing ``report_maintenance_request_scope`` isolates the report's
    obligation (translate the (restrict, user) verdict into the right
    ``or_filters``) from the helper's own role logic, which is covered in
    ``test_habitat_maintenance_scoping.py``.
    """

    # ----- maintenance_aging -----

    # Each report does ``from ...permissions import report_maintenance_request_scope``,
    # so the bound name lives in the REPORT module's namespace — patch it there, not
    # on the permissions module (the bare import would otherwise ignore an HP patch).

    def test_aging_scoped_user_gets_owner_assignee_or_filter(self):
        with patch.object(
            R_aging, "report_maintenance_request_scope", return_value=(True, "u@x.com")
        ), patch.object(R_aging.frappe, "get_all", return_value=[]) as ga:
            R_aging.execute({})
            self.assertEqual(
                _last_or_filters(ga), {"owner": "u@x.com", "assigned_to": "u@x.com"}
            )

    def test_aging_oversight_user_gets_no_or_filter(self):
        with patch.object(
            R_aging, "report_maintenance_request_scope", return_value=(False, "mgr@x.com")
        ), patch.object(R_aging.frappe, "get_all", return_value=[]) as ga:
            R_aging.execute({})
            self.assertIsNone(_last_or_filters(ga))

    # ----- open_maintenance_requests -----

    def test_backlog_scoped_user_gets_owner_assignee_or_filter(self):
        with patch.object(
            R_backlog, "report_maintenance_request_scope", return_value=(True, "u@x.com")
        ), patch.object(R_backlog.frappe, "get_all", return_value=[]) as ga:
            R_backlog.execute({})
            self.assertEqual(
                _last_or_filters(ga), {"owner": "u@x.com", "assigned_to": "u@x.com"}
            )

    def test_backlog_oversight_user_gets_no_or_filter(self):
        with patch.object(
            R_backlog, "report_maintenance_request_scope", return_value=(False, "mgr@x.com")
        ), patch.object(R_backlog.frappe, "get_all", return_value=[]) as ga:
            R_backlog.execute({})
            self.assertIsNone(_last_or_filters(ga))


class TestMaintenanceReportScopeIntegration(FrappeTestCase):
    """Real Maintenance Requests across three owners; real users; real row counts.

    A non-privileged requester must see ONLY the ticket they raised (``owner``)
    and a ticket assigned to them (``assigned_to``) — never a stranger's
    unrelated ticket. An oversight role (Accommodation Manager) sees every
    ticket. Both reports filter to OPEN statuses, so every seeded ticket is
    left in an open status to remain in scope.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=6).upper()

        cls.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "MRS Bldg " + cls.tag,
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
        cls.room = frappe.get_doc(
            {
                "doctype": "Room",
                "building": cls.building,
                "room_number": "MRS-" + cls.tag,
            }
        ).insert(ignore_permissions=True).name

        cls.requester = _user("mrs_requester@example.com", NON_PRIVILEGED_ROLE)
        cls.stranger = _user("mrs_stranger@example.com", NON_PRIVILEGED_ROLE)
        cls.manager = _user("mrs_manager@example.com", "Accommodation Manager")

        # owned by the requester (owner == requester)
        cls.t_owned = cls._ticket(owner=cls.requester, issue="Electrical")
        # owned by a stranger, assigned to the requester (assignee branch)
        cls.t_assigned = cls._ticket(
            owner=cls.stranger, issue="Plumbing", assigned_to=cls.requester
        )
        # owned by a stranger, unrelated to the requester (must stay hidden)
        cls.t_foreign = cls._ticket(owner=cls.stranger, issue="Furniture")

    @classmethod
    def _ticket(cls, owner, issue, assigned_to=None):
        """Insert a Maintenance Request whose ``owner`` is ``owner`` by inserting
        it AS that user, then return its name. Left in an OPEN status so both
        reports include it."""
        frappe.set_user(owner)
        try:
            doc = frappe.get_doc(
                {
                    "doctype": "Maintenance Request",
                    "building": cls.building,
                    "room": cls.room,
                    "issue_type": issue,
                    "issue_description": "MRS " + cls.tag + " " + issue,
                    "priority": "Medium",
                    "status": "Open",
                }
            )
            # ignore_permissions: the All-role create DocPerm governs intake in
            # production; the test only needs the row with owner == the inserter.
            doc.insert(ignore_permissions=True)
        finally:
            frappe.set_user("Administrator")

        if assigned_to:
            # set assignee + flip to Assigned (the controller requires assigned_to
            # for that status) as the privileged Administrator.
            doc.assigned_to = assigned_to
            doc.status = "Assigned"
            doc.save(ignore_permissions=True)
        return doc.name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _names_for(self, user, execute):
        frappe.set_user(user)
        seeded = {self.t_owned, self.t_assigned, self.t_foreign}
        return {r["name"] for r in execute({})[1] if r["name"] in seeded}

    # ----- maintenance_aging -----

    def test_aging_scoped_user_sees_only_owned_and_assigned(self):
        names = self._names_for(self.requester, R_aging.execute)
        self.assertEqual(
            names,
            {self.t_owned, self.t_assigned},
            "a non-privileged user sees only the tickets they raised or were assigned",
        )
        self.assertNotIn(self.t_foreign, names)

    def test_aging_oversight_sees_all_three(self):
        names = self._names_for(self.manager, R_aging.execute)
        self.assertEqual(
            names,
            {self.t_owned, self.t_assigned, self.t_foreign},
            "an oversight role sees every ticket",
        )

    # ----- open_maintenance_requests -----

    def test_backlog_scoped_user_sees_only_owned_and_assigned(self):
        names = self._names_for(self.requester, R_backlog.execute)
        self.assertEqual(names, {self.t_owned, self.t_assigned})
        self.assertNotIn(self.t_foreign, names)

    def test_backlog_oversight_sees_all_three(self):
        names = self._names_for(self.manager, R_backlog.execute)
        self.assertEqual(names, {self.t_owned, self.t_assigned, self.t_foreign})


if __name__ == "__main__":
    unittest.main()
