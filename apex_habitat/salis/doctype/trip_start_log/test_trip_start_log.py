# Copyright (c) 2026, AFMCO and contributors
"""Regression tests for Trip Start Log controller.

Run with:
    bench --site <site> run-tests --app apex_habitat \
        --module apex_habitat.salis.doctype.trip_start_log.test_trip_start_log
"""

from __future__ import annotations

import unittest

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError


class TestTripStartLogOwnership(unittest.TestCase):
    """P-036: a Salis Driver must not write another driver's Trip Start Log."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @classmethod
    def _make_user(cls, email: str, first_name: str) -> str:
        """Create (or reuse) a bare Frappe User with the Driver role."""
        if not frappe.db.exists("User", email):
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": first_name,
                    "send_welcome_email": 0,
                    "roles": [{"role": "Driver"}],
                }
            )
            user.insert(ignore_permissions=True)
        return email

    @classmethod
    def _make_driver(cls, user_email: str, full_name: str) -> str:
        """Create (or reuse) a Salis Driver linked to *user_email*."""
        existing = frappe.db.get_value(
            "Salis Driver", {"driver_user": user_email}, "name"
        )
        if existing:
            return existing
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": full_name,
                "driver_user": user_email,
            }
        )
        driver.insert(ignore_permissions=True)
        return driver.name

    # ------------------------------------------------------------------
    # set up / tear down
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")

        cls.user_a = cls._make_user(
            "test_driver_a@apex-test.example", "Test Driver A"
        )
        cls.user_b = cls._make_user(
            "test_driver_b@apex-test.example", "Test Driver B"
        )
        cls.driver_a = cls._make_driver(cls.user_a, "Test Driver A")
        cls.driver_b = cls._make_driver(cls.user_b, "Test Driver B")

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def _make_tsl_doc(self, driver_name: str) -> frappe.model.document.Document:
        """Return an *unsaved* TripStartLog stub with the given driver."""
        doc = frappe.new_doc("Trip Start Log")
        # Bypass the mandatory dispatch_trip link for the unit test: we only
        # need the driver field populated to exercise _check_driver_ownership.
        doc.driver = driver_name
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        return doc

    def test_driver_cannot_save_another_drivers_tsl(self):
        """Driver-A saving a TSL whose driver field is Driver-B → PermissionError."""
        frappe.set_user(self.user_a)
        doc = self._make_tsl_doc(self.driver_b)
        with self.assertRaises(FrappePermissionError):
            doc._check_driver_ownership()

    def test_driver_can_save_own_tsl(self):
        """Driver-A saving a TSL whose driver field is Driver-A → no error."""
        frappe.set_user(self.user_a)
        doc = self._make_tsl_doc(self.driver_a)
        # Must not raise.
        doc._check_driver_ownership()

    def test_administrator_is_unrestricted(self):
        """Administrator is never blocked regardless of the driver field."""
        frappe.set_user("Administrator")
        doc = self._make_tsl_doc(self.driver_b)
        # Must not raise.
        doc._check_driver_ownership()

    def test_non_driver_user_is_unrestricted(self):
        """A user with no Salis Driver record is not blocked."""
        # Use Administrator's session but pretend to be a user that has no
        # Salis Driver record (Administrator itself has no driver record).
        frappe.set_user("Administrator")
        doc = self._make_tsl_doc(self.driver_b)
        # Temporarily point session user to a plain user who has no driver.
        original = frappe.session.user
        frappe.session.user = "Guest"
        try:
            doc._check_driver_ownership()
        finally:
            frappe.session.user = original

    # ------------------------------------------------------------------
    # tear down — reset to Administrator so other tests are not affected
    # ------------------------------------------------------------------

    def tearDown(self):
        frappe.set_user("Administrator")
