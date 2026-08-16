# Copyright (c) 2026, AFMCO and contributors
"""Credential-first and session-only driver-resolution contract tests.

``get_driver_for_user`` prioritizes a presented driver credential: a valid one
returns its bound driver, while an invalid or blank one raises without session
fallback. With no credential it delegates to ``get_driver_for_session_user``,
whose explicit/session User lookup ignores cookies and returns None only when
that User is unlinked. The tests also keep the boarding and driver-portal aliases
delegated to the credential-aware helper.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
)
from apex.apex_core.utils import portal_identity as token_security
from apex.salis import utils
from apex.salis.api import boarding, driver_portal, fleet_employee
from apex.salis import permissions


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


BAD_TOKEN_SUBNET = "2001:db8:d41e::"


def _fresh_ip():
    """An address no other block in the app can be using: this file's own slice of
    the RFC 3849 documentation prefix, plus a random suffix.

    The portal bad-token window is keyed on the ADDRESS ALONE (one budget of
    ``BAD_TOKEN_ATTEMPTS_PER_MINUTE`` per IP, spent across every entry), so a
    shared ``127.0.0.1`` would let this file's failed cookies spend another test
    file's budget and turn somebody else's push red.
    """
    return BAD_TOKEN_SUBNET + frappe.generate_hash(length=12)


class _Request:
    def __init__(self, cookies, remote_addr):
        self.cookies = cookies
        self.remote_addr = remote_addr


@contextmanager
def _request_cookies(cookies):
    """One request surface per block, on its OWN address, leaving no window behind.

    The name handed to the cache on the way out is deliberately RAW:
    ``delete_value`` re-applies ``make_key`` (redis_wrapper.py:141-142), so an
    already-made key is prefixed a second time and clears nothing.
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


class TestGetDriverForUser(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []

        self.user = f"drv-{_h(12).lower()}@example.com"
        u = frappe.get_doc({
            "doctype": "User",
            "email": self.user,
            "first_name": "Driver " + _h(12),
            "send_welcome_email": 0,
        })
        u.insert(ignore_permissions=True)
        self._cleanup.append(("User", u.name))

        self.employee = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "EMP-" + _h(12),
            "naming_series": "HR-EMP-",
            "user_id": self.user,
        })
        self.employee.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", self.employee.name))

        self.driver = frappe.get_doc({
            "doctype": "Salis Driver",
            "naming_series": "DRV-.######",
            "full_name": "Driver " + _h(12),
            "employee": self.employee.name,
            "status": "Active",
        })
        self.driver.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Salis Driver", self.driver.name))

        self.unlinked_user = f"nolink-{_h(12).lower()}@example.com"
        nu = frappe.get_doc({
            "doctype": "User",
            "email": self.unlinked_user,
            "first_name": "Unlinked " + _h(12),
            "send_welcome_email": 0,
        })
        nu.insert(ignore_permissions=True)
        self._cleanup.append(("User", nu.name))

        self.other_driver = frappe.get_doc({
            "doctype": "Salis Driver",
            "naming_series": "DRV-.######",
            "full_name": "Other Driver " + _h(12),
            "status": "Active",
        })
        self.other_driver.insert(
            ignore_permissions=True,
            ignore_links=True,
            ignore_mandatory=True,
        )
        self._cleanup.append(("Salis Driver", self.other_driver.name))

        self._token_meta = frappe.get_meta("Masar Worker Token")
        self._original_token_autoname = self._token_meta.autoname
        self.addCleanup(
            setattr,
            self._token_meta,
            "autoname",
            self._original_token_autoname,
        )
        self._token_meta.autoname = "hash"
        self.driver_token = issue_driver_link(self.driver.name)["token"]
        self.other_driver_token = issue_driver_link(self.other_driver.name)["token"]
        for driver in (self.driver.name, self.other_driver.name):
            token_name = frappe.db.get_value(
                "Masar Worker Token",
                {"holder_type": "Driver", "driver": driver},
                "name",
            )
            self._cleanup.append(("Masar Worker Token", token_name))

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
            with _request_cookies({}):
                self.assertEqual(utils.get_driver_for_user(), self.driver.name)
        finally:
            frappe.set_user("Administrator")

    def test_bad_presented_cookie_never_falls_back_to_linked_session(self):
        """A garbage or blank credential is refused outright, never silently
        dropped back to the session's linked driver."""
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(
                frappe.PermissionError,
                msg="a garbage cookie must not fall back to the linked session",
            ):
                utils.get_driver_for_user()
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(
                frappe.PermissionError,
                msg="a blank cookie must not fall back to the linked session",
            ):
                utils.get_driver_for_user()

    def test_session_resolution_survives_absent_or_cookieless_request(self):
        """The session-only fallback works whether the request carries an
        empty cookie jar or no request object exists at all."""
        frappe.set_user(self.user)
        with _request_cookies({}):
            self.assertEqual(
                utils.get_driver_for_user(),
                self.driver.name,
                "an empty cookie jar still resolves via the session",
            )
        with _without_request():
            self.assertEqual(
                utils.get_driver_for_user(),
                self.driver.name,
                "no request object at all still resolves via the session",
            )

    def test_valid_cookie_precedes_explicit_linked_user(self):
        frappe.set_user(self.user)
        binding = frappe.db.get_value(
            "Masar Worker Token",
            {"holder_type": "Driver", "driver": self.other_driver.name},
            ["holder_type", "party_type", "party", "employee", "driver"],
            as_dict=True,
        )
        self.assertEqual(
            dict(binding),
            {
                "holder_type": "Driver",
                "party_type": None,
                "party": None,
                "employee": None,
                "driver": self.other_driver.name,
            },
        )
        with _request_cookies({"masar_dt": self.other_driver_token}):
            self.assertEqual(
                utils.get_driver_for_user(self.user),
                self.other_driver.name,
            )

    def test_invalid_cookie_precedes_explicit_linked_user(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(frappe.PermissionError):
                utils.get_driver_for_user(self.user)

    def test_session_only_resolution_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": self.other_driver_token}):
            self.assertEqual(
                utils.get_driver_for_session_user(self.user),
                self.driver.name,
            )

    def test_each_request_block_gets_a_private_bad_token_window(self):
        """Non-vacuous isolation: every block starts on an address whose window is
        EMPTY (so the counter reads 1, not 2), and leaves no window behind.

        A shared address would pool this file's three charged failures with another
        file's into one 10-per-minute budget, and the eleventh would answer 429
        where a test asserted PermissionError -- red on whoever pushed next.
        """
        frappe.set_user(self.user)
        addresses = []
        for _ in range(2):
            with _request_cookies({"masar_dt": "invalid"}) as ip:
                addresses.append(ip)
                name = token_security.BAD_TOKEN_WINDOW_KEY.format(ip)
                with self.assertRaises(frappe.PermissionError):
                    utils.get_driver_for_user()
                self.assertEqual(
                    int(frappe.cache.get(frappe.cache.make_key(name)) or 0),
                    1,
                    "a reused address would carry another block's failed attempts",
                )
            self.assertIsNone(
                frappe.cache.get(frappe.cache.make_key(name)),
                f"the throttle window {name} outlived its cleanup",
            )
        self.assertNotEqual(addresses[0], addresses[1])

    def test_cookie_context_restores_previously_absent_request_state(self):
        sentinel = object()
        previous_request = getattr(frappe.local, "request", sentinel)
        previous_ip = getattr(frappe.local, "request_ip", sentinel)
        for fieldname in ("request", "request_ip"):
            if hasattr(frappe.local, fieldname):
                delattr(frappe.local, fieldname)
        try:
            with _request_cookies({"masar_dt": self.driver_token}):
                self.assertTrue(hasattr(frappe.local, "request"))
                self.assertTrue(hasattr(frappe.local, "request_ip"))
            self.assertFalse(hasattr(frappe.local, "request"))
            self.assertFalse(hasattr(frappe.local, "request_ip"))
        finally:
            for fieldname, previous in (
                ("request", previous_request),
                ("request_ip", previous_ip),
            ):
                if previous is not sentinel:
                    setattr(frappe.local, fieldname, previous)

    def test_fleet_vehicle_endpoint_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": self.other_driver_token}), patch.object(
            fleet_employee, "bound_vehicle", return_value=None
        ) as bound:
            self.assertEqual(fleet_employee.get_my_vehicle(), {"vehicle": None})
        bound.assert_called_once_with(self.driver.name)

    def test_fleet_fuel_endpoint_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": self.other_driver_token}), patch.object(
            fleet_employee, "bound_vehicle", return_value=None
        ) as bound, self.assertRaises(frappe.ValidationError):
            fleet_employee.submit_fuel_request(10)
        bound.assert_called_once_with(self.driver.name)

    def test_dispatch_permission_hook_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        trip = frappe._dict(doctype="Dispatch Trip", driver=self.driver.name)
        with _request_cookies({"masar_dt": self.other_driver_token}):
            self.assertIsNone(
                permissions.project_scoped_has_permission(
                    trip,
                    "read",
                    user=self.user,
                )
            )

    def test_aliases_match_helper_for_linked_user(self):
        expected = self.driver.name
        self.assertEqual(driver_portal._find_driver(self.user), expected)
        self.assertEqual(boarding._driver_for_user(self.user), expected)
        self.assertEqual(driver_portal._resolve_driver(self.user), expected)

    def test_aliases_return_none_for_unlinked_user(self):
        self.assertIsNone(driver_portal._find_driver(self.unlinked_user))
        self.assertIsNone(boarding._driver_for_user(self.unlinked_user))

    def test_resolve_driver_throws_for_unlinked_user(self):
        with self.assertRaises(frappe.PermissionError):
            driver_portal._resolve_driver(self.unlinked_user)

    def test_aliases_delegate_to_shared_helper(self):
        """Both boarding and driver-portal aliases forward to the one
        credential-aware resolver instead of re-implementing it."""
        with patch.object(driver_portal, "get_driver_for_user", return_value="SENTINEL") as m:
            self.assertEqual(
                driver_portal._find_driver("someone@example.com"),
                "SENTINEL",
                "driver_portal._find_driver must return the shared helper's result",
            )
        m.assert_called_once_with("someone@example.com")

        with patch.object(boarding, "get_driver_for_user", return_value="SENTINEL") as m:
            self.assertEqual(
                boarding._driver_for_user("someone@example.com"),
                "SENTINEL",
                "boarding._driver_for_user must return the shared helper's result",
            )
        m.assert_called_once_with("someone@example.com")
