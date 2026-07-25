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
from apex.salis import utils
from apex.salis.api import boarding, driver_portal, fleet_employee
from apex.salis import permissions


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class _Request:
    def __init__(self, cookies):
        self.cookies = cookies


@contextmanager
def _request_cookies(cookies):
    sentinel = object()
    previous_request = getattr(frappe.local, "request", sentinel)
    previous_ip = getattr(frappe.local, "request_ip", sentinel)
    frappe.local.request = _Request(cookies)
    frappe.local.request_ip = "127.0.0.1"
    try:
        yield
    finally:
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

        # [#cjb30p]
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

        # [#j434ox]
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

    def test_invalid_cookie_never_falls_back_to_linked_session(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(frappe.PermissionError):
                utils.get_driver_for_user()

    def test_blank_presented_cookie_never_falls_back_to_linked_session(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(frappe.PermissionError):
                utils.get_driver_for_user()

    def test_absent_cookie_preserves_explicit_session_preview(self):
        frappe.set_user(self.user)
        with _request_cookies({}):
            self.assertEqual(utils.get_driver_for_user(), self.driver.name)

    def test_missing_request_preserves_explicit_session_preview(self):
        frappe.set_user(self.user)
        with _without_request():
            self.assertEqual(utils.get_driver_for_user(), self.driver.name)

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
            fleet_employee, "_bound_vehicle", return_value=None
        ) as bound_vehicle:
            self.assertEqual(fleet_employee.get_my_vehicle(), {"vehicle": None})
        bound_vehicle.assert_called_once_with(self.driver.name)

    def test_fleet_trips_endpoint_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": self.other_driver_token}), patch.object(
            fleet_employee.frappe, "get_all", return_value=[]
        ) as get_all:
            self.assertEqual(fleet_employee.get_my_recent_trips(), [])
        self.assertEqual(get_all.call_args.kwargs["filters"]["driver"], self.driver.name)

    def test_fleet_fuel_endpoint_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        with _request_cookies({"masar_dt": self.other_driver_token}), patch.object(
            fleet_employee, "_bound_vehicle", return_value=None
        ) as bound_vehicle, self.assertRaises(frappe.ValidationError):
            fleet_employee.submit_fuel_request(10)
        bound_vehicle.assert_called_once_with(self.driver.name)

    def test_dispatch_permission_hook_ignores_foreign_driver_cookie(self):
        frappe.set_user(self.user)
        trip = frappe._dict(driver=self.driver.name)
        with _request_cookies({"masar_dt": self.other_driver_token}):
            self.assertIsNone(
                permissions.dispatch_trip_has_permission(
                    trip,
                    "read",
                    user=self.user,
                )
            )

    def test_aliases_match_helper_for_linked_user(self):
        expected = self.driver.name
        self.assertEqual(driver_portal._find_driver(self.user), expected)
        self.assertEqual(boarding._driver_for_user(self.user), expected)
        # [#9s8s6u]
        self.assertEqual(driver_portal._resolve_driver(self.user), expected)

    def test_aliases_return_none_for_unlinked_user(self):
        self.assertIsNone(driver_portal._find_driver(self.unlinked_user))
        self.assertIsNone(boarding._driver_for_user(self.unlinked_user))

    def test_resolve_driver_throws_for_unlinked_user(self):
        # [#a8a9nq]
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
