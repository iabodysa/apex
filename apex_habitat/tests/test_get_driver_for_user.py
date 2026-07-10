# Copyright (c) 2026, AFMCO and contributors
"""Shared driver-resolution helper.

``salis.utils.get_driver_for_user`` is the single user -> Employee (user_id) ->
Salis Driver (employee) resolver. The two former in-module copies are now thin
aliases of it:

  * ``boarding._driver_for_user``
  * ``driver_portal._find_driver`` (which ``driver_portal._resolve_driver`` and,
    transitively, masar rely on)

This proves: a LINKED user resolves to their driver, an UNLINKED user resolves to
None (the prior soft behaviour, never a throw), every alias returns the SAME value
as the shared helper, and each alias actually delegates to it (so the resolution
can never drift again).
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis import utils
from apex_habitat.salis.api import boarding, driver_portal


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestGetDriverForUser(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        # A user linked through Employee.user_id to a Salis Driver.
        self.user = f"drv-{_h(6).lower()}@example.com"
        u = frappe.get_doc({
            "doctype": "User",
            "email": self.user,
            "first_name": "Driver " + _h(4),
            "send_welcome_email": 0,
        })
        u.insert(ignore_permissions=True)
        self._cleanup.append(("User", u.name))

        self.employee = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "EMP-" + _h(6),
            "naming_series": "HR-EMP-",
            "user_id": self.user,
        })
        self.employee.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", self.employee.name))

        self.driver = frappe.get_doc({
            "doctype": "Salis Driver",
            "naming_series": "DRV-.######",
            "full_name": "Driver " + _h(4),
            "employee": self.employee.name,
        })
        self.driver.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Salis Driver", self.driver.name))

        # A user with no Employee link at all (the unlinked case).
        self.unlinked_user = f"nolink-{_h(6).lower()}@example.com"
        nu = frappe.get_doc({
            "doctype": "User",
            "email": self.unlinked_user,
            "first_name": "Unlinked " + _h(4),
            "send_welcome_email": 0,
        })
        nu.insert(ignore_permissions=True)
        self._cleanup.append(("User", nu.name))

    def tearDown(self):
        frappe.set_user("Administrator")
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    def test_linked_user_resolves_to_driver(self):
        self.assertEqual(utils.get_driver_for_user(self.user), self.driver.name)

    def test_unlinked_user_resolves_to_none(self):
        self.assertIsNone(utils.get_driver_for_user(self.unlinked_user))

    def test_defaults_to_session_user(self):
        frappe.set_user(self.user)
        try:
            self.assertEqual(utils.get_driver_for_user(), self.driver.name)
        finally:
            frappe.set_user("Administrator")

    def test_aliases_match_helper_for_linked_user(self):
        expected = self.driver.name
        self.assertEqual(driver_portal._find_driver(self.user), expected)
        self.assertEqual(boarding._driver_for_user(self.user), expected)
        # _resolve_driver (used by masar) wraps _find_driver -> same value.
        self.assertEqual(driver_portal._resolve_driver(self.user), expected)

    def test_aliases_return_none_for_unlinked_user(self):
        self.assertIsNone(driver_portal._find_driver(self.unlinked_user))
        self.assertIsNone(boarding._driver_for_user(self.unlinked_user))

    def test_resolve_driver_throws_for_unlinked_user(self):
        # The hard wrapper masar/action endpoints use still fails closed on None.
        with self.assertRaises(frappe.PermissionError):
            driver_portal._resolve_driver(self.unlinked_user)

    def test_find_driver_delegates_to_shared_helper(self):
        with patch.object(driver_portal, "get_driver_for_user", return_value="SENTINEL") as m:
            self.assertEqual(driver_portal._find_driver("someone@example.com"), "SENTINEL")
        m.assert_called_once_with("someone@example.com")

    def test_driver_for_user_delegates_to_shared_helper(self):
        with patch.object(boarding, "get_driver_for_user", return_value="SENTINEL") as m:
            self.assertEqual(boarding._driver_for_user("someone@example.com"), "SENTINEL")
        m.assert_called_once_with("someone@example.com")
