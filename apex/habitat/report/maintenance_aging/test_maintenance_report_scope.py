# Copyright (c) 2026, AFMCO and contributors
"""Owner/assignee row-scoping for the Maintenance Aging Script Report.

``frappe.get_all`` forces ``ignore_permissions=True``, so the owner/assignee
row-scoping the Maintenance Request desk list gets via
``maintenance_request_query`` (permission_query_conditions) is BYPASSED inside
``maintenance_aging`` — a non-privileged user running the report would otherwise
see EVERY ticket's row. The report's ``execute()``
re-applies the caller's owner/assignee scope via
``permissions.report_maintenance_request_scope`` (handed to get_all as
``or_filters``), while the privileged oversight roles in
``permissions.PRIVILEGED_ROLES`` still see everything.

Two layers of proof, mirroring ``tests/test_report_scope.py``:

* :class:`TestMaintenanceReportScopeLogic` patches the scope helper and asserts
  the ``or_filters`` the report hands to ``frappe.get_all`` (scoped ->
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

from apex.habitat.report.maintenance_aging import maintenance_aging as R_aging
from apex.tests._helpers import _user

NON_PRIVILEGED_ROLE = "Blogger"


def _last_or_filters(mock_get_all):
    """The ``or_filters`` kwarg passed to the report's (only) frappe.get_all."""
    return mock_get_all.call_args.kwargs.get("or_filters")


class TestMaintenanceReportScopeLogic(FrappeTestCase):
    """The owner/assignee or_filters the report applies, helper stubbed.

    Stubbing ``report_maintenance_request_scope`` isolates the report's
    obligation (translate the (restrict, user) verdict into the right
    ``or_filters``) from the helper's own role logic, which is covered in
    ``test_habitat_maintenance_scoping.py``.
    """



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


class TestMaintenanceReportScopeIntegration(FrappeTestCase):
    """Real Maintenance Requests across three owners; real users; real row counts.

    A non-privileged requester must see ONLY the ticket they raised (``owner``)
    and a ticket assigned to them (``assigned_to``) — never a stranger's
    unrelated ticket. An oversight role (Accommodation Manager) sees every
    ticket. The report filters to OPEN statuses, so every seeded ticket is
    left in an open status to remain in scope.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

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

        cls.t_owned = cls._ticket(owner=cls.requester, issue="Electrical")
        cls.t_assigned = cls._ticket(
            owner=cls.stranger, issue="Plumbing", assigned_to=cls.requester
        )
        cls.t_foreign = cls._ticket(owner=cls.stranger, issue="Furniture")

    @classmethod
    def _ticket(cls, owner, issue, assigned_to=None):
        """A SUBMITTED Maintenance Request whose ``owner`` is ``owner``, by inserting
        it AS that user; returns its name.

        Submitted because the report filters ``docstatus: 1`` — a draft would never
        reach it and every row assertion would grade an empty set. ``assigned_to`` is
        set on the draft rather than afterwards: the field is not allow_on_submit, and
        ``status`` is never written by hand at all, because ``_guard_status``
        (maintenance_request.py:56) refuses any status change outside the server
        actions. "Open" is what a new request takes and is in the report's open set.
        """
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
                    "assigned_to": assigned_to,
                }
            )
            doc.insert(ignore_permissions=True)
        finally:
            frappe.set_user("Administrator")

        doc.flags.ignore_permissions = True
        doc.submit()
        return doc.name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _names_for(self, user, execute):
        frappe.set_user(user)
        seeded = {self.t_owned, self.t_assigned, self.t_foreign}
        return {r["name"] for r in execute({})[1] if r["name"] in seeded}


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


if __name__ == "__main__":
    unittest.main()
