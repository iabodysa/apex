# Copyright (c) 2026, AFMCO and contributors
"""Regression tests for Trip Start Log controller.

Run with:
    bench --site <site> run-tests --app apex_habitat \
        --module apex_habitat.salis.doctype.trip_start_log.test_trip_start_log
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

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


class TestTripStartLogBoardingDedup(unittest.TestCase):
    """P-037: the same passenger must not board twice on one Trip Start Log.

    A duplicate boarding row inflates ``boarded_count`` and corrupts the
    expected-vs-boarded headcount reconciliation. ``_validate_boarding_rows``
    guards both worker classes: a registered Employee (``worker``) and an
    unregistered contractor/temp (``contractor_id`` / ``worker_name``)."""

    def _make_log(self, rows):
        """Return an unsaved Trip Start Log with the given boarding rows.

        Each row dict is appended to boarding_events; we exercise the in-memory
        validator directly (no insert) so the test is fast and self-contained."""
        doc = frappe.new_doc("Trip Start Log")
        for row in rows:
            doc.append("boarding_events", row)
        return doc

    def test_duplicate_registered_worker_throws(self):
        doc = self._make_log(
            [{"worker": "EMP-DEDUP-1"}, {"worker": "EMP-DEDUP-1"}]
        )
        with self.assertRaises(frappe.ValidationError):
            doc._validate_boarding_rows()

    def test_distinct_registered_workers_pass(self):
        doc = self._make_log(
            [{"worker": "EMP-DEDUP-1"}, {"worker": "EMP-DEDUP-2"}]
        )
        # Must not raise.
        doc._validate_boarding_rows()

    def test_duplicate_unregistered_worker_throws(self):
        # Case-insensitive: a casing variant must not slip a second boarding past.
        doc = self._make_log(
            [
                {"is_unregistered": 1, "contractor_id": "C-99"},
                {"is_unregistered": 1, "contractor_id": "c-99"},
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            doc._validate_boarding_rows()


class TestTripStartLogTripContext(unittest.TestCase):
    """P-041: _resolve_trip_context backfills both fields from the SAME Dispatch
    Trip row in exactly ONE db.get_value call (no N+1 of two sequential reads)."""

    def _make_log(self, **fields):
        doc = frappe.new_doc("Trip Start Log")
        for k, v in fields.items():
            setattr(doc, k, v)
        return doc

    def test_single_db_call_populates_both_fields(self):
        doc = self._make_log(dispatch_trip="DT-001")  # both context fields empty
        captured = {}

        def _fake_get_value(doctype, name, fieldname, **kwargs):
            captured["doctype"] = doctype
            captured["fieldname"] = fieldname
            captured["as_dict"] = kwargs.get("as_dict")
            return frappe._dict(transport_request="TR-7", route_plan="RP-3")

        with patch(
            "apex_habitat.salis.doctype.trip_start_log.trip_start_log.frappe.db.get_value",
            side_effect=_fake_get_value,
        ) as mocked:
            doc._resolve_trip_context()

        # Exactly one round-trip to Dispatch Trip, asking for both columns at once.
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(captured["doctype"], "Dispatch Trip")
        self.assertEqual(captured["fieldname"], ["transport_request", "route_plan"])
        self.assertTrue(captured["as_dict"])
        # Both fields backfilled from that single row.
        self.assertEqual(doc.transport_request, "TR-7")
        self.assertEqual(doc.route_plan, "RP-3")

    def test_no_db_call_when_both_already_set(self):
        doc = self._make_log(
            dispatch_trip="DT-001", transport_request="TR-7", route_plan="RP-3"
        )
        with patch(
            "apex_habitat.salis.doctype.trip_start_log.trip_start_log.frappe.db.get_value",
            side_effect=AssertionError("must not query when both fields are set"),
        ) as mocked:
            doc._resolve_trip_context()
        mocked.assert_not_called()
