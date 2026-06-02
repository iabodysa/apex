"""Owner-scoping tests for the Habitat Maintenance Request permission layer.

Maintenance Request intake is universal: any user can raise a ticket (the
All-role create DocPerm), but a non-privileged user must only ever see the
tickets they own (raised) or are assigned to — never anyone else's. A small set
of privileged oversight roles (System Manager, Accommodation Manager, Resident
Supervisor, Resident Request Coordinator) and the Administrator see everything.

These tests drive the query/has_permission functions directly so they exercise
the exact code path the desk list view and the per-document access check hit.
"""

import unittest

import frappe

from apex_habitat.habitat.permissions import (
    PRIVILEGED_ROLES,
    maintenance_request_has_permission,
    maintenance_request_query,
)
from apex_habitat.tests._helpers import _user


def _ensure_role(name):
    """Idempotently ensure a desk Role exists.

    Some privileged roles in PRIVILEGED_ROLES (e.g. Resident Request
    Coordinator) are provisioned by the role-bootstrap seeder, which may not
    have run on the test site yet. These tests exercise the permission layer in
    isolation, so they create any missing role themselves rather than coupling
    to seeder ordering. Create-only / idempotent.
    """
    if not frappe.db.exists("Role", name):
        frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(
            ignore_permissions=True
        )
    return name


# A guaranteed-present, non-privileged desk role. Using a stock Frappe role
# keeps the "ordinary raiser" fixtures independent of the Habitat role seeder
# (the resident-facing roles are not provisioned on a bare test site).
NON_PRIVILEGED_ROLE = "Blogger"


class TestMaintenanceRequestQuery(unittest.TestCase):
    """permission_query_conditions fragment: '' for privileged, owner-scope
    otherwise, '1=0' for Guest."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _ensure_role("Resident Request Coordinator")
        # A non-privileged user that can raise tickets but not oversee them.
        cls.requester = _user("mr_requester@example.com", NON_PRIVILEGED_ROLE)
        # Privileged oversight roles.
        cls.coordinator = _user(
            "mr_coordinator@example.com", "Resident Request Coordinator"
        )
        cls.manager = _user("mr_manager@example.com", "Accommodation Manager")
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_administrator_has_no_restriction(self):
        self.assertEqual(maintenance_request_query(user="Administrator"), "")

    def test_privileged_role_has_no_restriction(self):
        self.assertEqual(maintenance_request_query(user=self.coordinator), "")
        self.assertEqual(maintenance_request_query(user=self.manager), "")

    def test_guest_sees_nothing(self):
        self.assertEqual(maintenance_request_query(user="Guest"), "1=0")

    def test_non_privileged_user_is_owner_scoped(self):
        frag = maintenance_request_query(user=self.requester)
        escaped = frappe.db.escape(self.requester)
        self.assertEqual(
            frag,
            "(`owner` = {0} or `assigned_to` = {0})".format(escaped),
        )

    def test_query_defaults_to_session_user(self):
        frappe.set_user(self.requester)
        try:
            frag = maintenance_request_query()
        finally:
            frappe.set_user("Administrator")
        escaped = frappe.db.escape(self.requester)
        self.assertEqual(
            frag,
            "(`owner` = {0} or `assigned_to` = {0})".format(escaped),
        )

    def test_escaping_is_used(self):
        """A user value must be passed through frappe.db.escape, so a value
        containing a quote is neutralised rather than inlined raw (no injection).
        """
        evil = "x' or '1'='1"
        frag = maintenance_request_query(user=evil)
        # The escaped form is present verbatim...
        self.assertIn(frappe.db.escape(evil), frag)
        # ...and the raw, unescaped break-out string never appears unescaped.
        self.assertNotIn("= x' or '1'='1", frag)


class TestMaintenanceRequestHasPermission(unittest.TestCase):
    """has_permission contract: None (defer) for privileged, True only when the
    non-privileged user owns or is assigned the doc, else False."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        _ensure_role("Resident Request Coordinator")
        cls.owner = _user("mr_owner@example.com", NON_PRIVILEGED_ROLE)
        cls.assignee = _user("mr_assignee@example.com", NON_PRIVILEGED_ROLE)
        cls.stranger = _user("mr_stranger@example.com", NON_PRIVILEGED_ROLE)
        cls.coordinator = _user(
            "mr_perm_coordinator@example.com", "Resident Request Coordinator"
        )
        frappe.db.commit()

    def _doc(self, owner=None, assigned_to=None):
        return frappe._dict(
            {
                "doctype": "Maintenance Request",
                "owner": owner,
                "assigned_to": assigned_to,
            }
        )

    def test_privileged_defers_to_standard(self):
        self.assertIsNone(
            maintenance_request_has_permission(
                self._doc(owner=self.owner), "read", user=self.coordinator
            )
        )

    def test_administrator_defers_to_standard(self):
        self.assertIsNone(
            maintenance_request_has_permission(
                self._doc(owner=self.owner), "read", user="Administrator"
            )
        )

    def test_owner_allowed(self):
        self.assertTrue(
            maintenance_request_has_permission(
                self._doc(owner=self.owner), "read", user=self.owner
            )
        )

    def test_assignee_allowed(self):
        self.assertTrue(
            maintenance_request_has_permission(
                self._doc(owner=self.stranger, assigned_to=self.assignee),
                "read",
                user=self.assignee,
            )
        )

    def test_non_owner_non_assignee_denied(self):
        self.assertFalse(
            maintenance_request_has_permission(
                self._doc(owner=self.owner, assigned_to=self.assignee),
                "read",
                user=self.stranger,
            )
        )

    def test_has_permission_defaults_to_session_user(self):
        frappe.set_user(self.owner)
        try:
            result = maintenance_request_has_permission(
                self._doc(owner=self.owner), "read"
            )
        finally:
            frappe.set_user("Administrator")
        self.assertTrue(result)


class TestPrivilegedRolesConstant(unittest.TestCase):
    def test_expected_privileged_roles(self):
        self.assertEqual(
            PRIVILEGED_ROLES,
            {
                "System Manager",
                "Accommodation Manager",
                "Resident Supervisor",
                "Resident Request Coordinator",
            },
        )


if __name__ == "__main__":
    unittest.main()
