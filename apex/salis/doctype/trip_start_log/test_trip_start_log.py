# Copyright (c) 2026, AFMCO and contributors
"""Regression tests for Trip Start Log controller.

Run with:
    ../env/bin/python ../apps/apex/.claude/tools/run_suite_file.py ci.localhost \
        ../apps/apex/.claude/tests/apex/salis/doctype/trip_start_log/test_trip_start_log.py
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
)
from apex.apex_core.utils import portal_identity as token_security

BAD_TOKEN_SUBNET = "2001:db8:751c::"


def _h(n: int = 12) -> str:
    return frappe.generate_hash(length=n).upper()


def _fresh_ip() -> str:
    """An address no other test block can be spending, from this file's own slice
    of the RFC 3849 documentation prefix.

    The portal bad-token window is keyed on the ADDRESS ALONE, so a shared
    127.0.0.1 would let this file's rejected cookies burn another file's budget
    and answer 429 where a test asserted PermissionError.
    """
    return BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)


class _Request:
    def __init__(self, cookies, remote_addr):
        self.cookies = cookies
        self.remote_addr = remote_addr


@contextmanager
def _request_cookies(cookies):
    """One request surface per block, on its own address, leaving no window behind.

    The key handed back to the cache is RAW because ``delete_value`` re-applies
    ``make_key`` (redis_wrapper.py:141-142), so an already-made key would be
    prefixed twice and clear nothing.
    """
    ip = _fresh_ip()
    sentinel = object()
    previous_request = getattr(frappe.local, "request", sentinel)
    previous_ip = getattr(frappe.local, "request_ip", sentinel)
    frappe.local.request = _Request(cookies, ip)
    frappe.local.request_ip = ip
    try:
        yield ip
    finally:
        frappe.cache.delete_value(token_security.BAD_TOKEN_WINDOW_KEY.format(ip))
        for fieldname, previous in (
            ("request", previous_request),
            ("request_ip", previous_ip),
        ):
            if previous is sentinel:
                if hasattr(frappe.local, fieldname):
                    delattr(frappe.local, fieldname)
            else:
                setattr(frappe.local, fieldname, previous)


@contextmanager
def _without_request():
    """No request at all — a scheduled job, a patch, or ``bench migrate``."""
    sentinel = object()
    previous = getattr(frappe.local, "request", sentinel)
    if previous is not sentinel:
        del frappe.local.request
    try:
        yield
    finally:
        if previous is sentinel:
            if hasattr(frappe.local, "request"):
                del frappe.local.request
        else:
            frappe.local.request = previous


class TestTripStartLogOwnership(FrappeTestCase):
    """A driver may only write their OWN Trip Start Log, and after the barcode
    cutover their identity is a bearer token, not a Frappe User.

    Every case here goes through a real ``insert``, not a direct call to the
    guard, because the ownership decision depends on a value the framework fills
    in on the way: ``driver`` is ``fetch_from: dispatch_trip.driver`` and
    ``_validate_links`` runs BEFORE the controller's ``validate``
    (document.py:302-310), so what the guard sees is the trip's driver — exactly
    what a crafted save would carry. The portal writes this log with
    ``ignore_permissions``, so the guard is the last line, not a second opinion
    on top of a DocPerm.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.driver_a = self._make_driver("Token Driver A")
        self.driver_b = self._make_driver("Token Driver B")
        self.token_a = self._issue(self.driver_a)
        self._issue(self.driver_b)
        self.trip_a = self._make_trip(self.driver_a)
        self.trip_b = self._make_trip(self.driver_b)

        self.desk_user, self.desk_driver = self._make_session_linked_driver()

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype, name in reversed(self._cleanup):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _track(self, doctype: str, name: str) -> str:
        self._cleanup.append((doctype, name))
        return name

    def _make_driver(self, label: str) -> str:
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "naming_series": "DRV-.######",
                "full_name": f"{label} {_h(12)}",
                "status": "Active",
            }
        )
        driver.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return self._track("Salis Driver", driver.name)

    def _issue(self, driver: str) -> str:
        raw = issue_driver_link(driver)["token"]
        self._track(
            "Masar Worker Token",
            frappe.db.get_value(
                "Masar Worker Token", {"holder_type": "Driver", "driver": driver}, "name"
            ),
        )
        return raw

    def _make_trip(self, driver: str) -> str:
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "driver": driver,
                "trip_date": frappe.utils.today(),
                "status": "Planned",
            }
        )
        trip.insert(ignore_permissions=True)
        return self._track("Dispatch Trip", trip.name)

    def _make_session_linked_driver(self) -> tuple[str, str]:
        """A driver who still has a Frappe User, through the Employee link the
        session fallback reads. The surviving legacy path, kept for the desk."""
        email = f"desk-drv-{_h(12).lower()}@example.com"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Desk Driver " + _h(12),
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
        self._track("User", email)

        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "EMP-" + _h(12),
                "naming_series": "HR-EMP-",
                "user_id": email,
            }
        )
        employee.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._track("Employee", employee.name)

        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "naming_series": "DRV-.######",
                "full_name": "Desk Driver " + _h(12),
                "employee": employee.name,
                "status": "Active",
            }
        )
        driver.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return email, self._track("Salis Driver", driver.name)

    def _save_log(self, dispatch_trip: str):
        """Save a Trip Start Log against a trip exactly as the portal does."""
        doc = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dispatch_trip,
                "status": "Started",
                "start_datetime": frappe.utils.now_datetime(),
            }
        )
        doc.insert(ignore_permissions=True)
        self._track("Trip Start Log", doc.name)
        return doc

    def test_token_driver_cannot_save_another_drivers_log(self):
        """Driver A's credential, driver B's trip → refused.

        This is the shipped hole the barcode cutover left: with the driver read
        from ``frappe.session.user`` the session is Guest, nothing resolved, and
        the guard returned before it compared anything.
        """
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": self.token_a}):
            with self.assertRaises(FrappePermissionError):
                self._save_log(self.trip_b)

    def test_token_driver_can_save_own_log(self):
        """Driver A's credential, driver A's trip → saved, and owned by A."""
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": self.token_a}):
            doc = self._save_log(self.trip_a)
        self.assertEqual(doc.driver, self.driver_a)

    def test_invalid_credential_is_refused_rather_than_waved_through(self):
        """A presented credential that does not resolve can never reach the
        permissive branch: the resolver raises instead of returning None."""
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": "not-a-real-token"}):
            with self.assertRaises(FrappePermissionError):
                self._save_log(self.trip_a)

    def test_session_linked_driver_cannot_save_another_drivers_log(self):
        """The surviving User -> Employee -> Salis Driver path still scopes a
        signed-in driver to their own record when no credential is presented."""
        frappe.set_user(self.desk_user)
        with _request_cookies({}):
            with self.assertRaises(FrappePermissionError):
                self._save_log(self.trip_b)

    def test_desk_user_who_is_not_a_driver_is_unrestricted(self):
        """A Fleet Manager / Supervisor session resolves to no driver and must
        keep saving any trip's log — this guard scopes drivers, not staff."""
        email = f"fleet-{_h(12).lower()}@example.com"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Fleet Staff " + _h(12),
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Manager"}],
            }
        ).insert(ignore_permissions=True)
        self._track("User", email)

        frappe.set_user(email)
        with _request_cookies({}):
            doc = self._save_log(self.trip_b)
        self.assertEqual(doc.driver, self.driver_b)

    def test_no_request_context_is_unrestricted(self):
        """A scheduled job, a patch or a migrate carries no request and no
        driver-linked User, and must not start throwing."""
        frappe.set_user("Guest")
        with _without_request():
            doc = self._save_log(self.trip_b)
        self.assertEqual(doc.driver, self.driver_b)

    def test_administrator_is_unrestricted(self):
        doc = self._save_log(self.trip_b)
        self.assertEqual(doc.driver, self.driver_b)


class TestTripStartLogBoardingDedup(unittest.TestCase):
    """the same passenger must not board twice on one Trip Start Log.

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
        doc._validate_boarding_rows()

    def test_duplicate_unregistered_worker_throws(self):
        doc = self._make_log(
            [
                {"is_unregistered": 1, "contractor_id": "C-99"},
                {"is_unregistered": 1, "contractor_id": "c-99"},
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            doc._validate_boarding_rows()
