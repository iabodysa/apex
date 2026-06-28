# Copyright (c) 2026, AFMCO and contributors
"""P-038 regression: Dispatch Trip driver-own row scoping.

Dispatch Trip is registered in ``permission_query_conditions``
(``dispatch_trip_query``) and ``has_permission`` (``dispatch_trip_has_permission``).
A Driver reaches a trip only through the identity-scoped driver-portal API
(``my_trips_*`` uses ``frappe.get_all`` filtered on the resolved driver), and the
Driver role holds NO desk read DocPerm on Dispatch Trip — so the desk list is
closed to drivers by DocPerm alone.

These tests lock down the second layer: the ``dispatch_trip_query`` driver-own
SQL fragment must select the acting driver's OWN trips and exclude another
driver's, and ``dispatch_trip_has_permission`` must allow a driver on their own
trip and deny on another's. The own-driver basis is resolved through the
``User -> Employee.user_id -> Salis Driver.employee`` chain (the same chain
``get_driver_for_user`` and ``_own_driver_trips_condition`` use), NOT through the
fetched ``driver_user`` mirror.

A scoped supervisor (project User Permission, no driver) sees only their
project's trips; the driver-own clause must not leak another driver's trip to
them either.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.permissions import (
    dispatch_trip_has_permission,
    dispatch_trip_query,
)
from apex_habitat.tests._helpers import _user


def _employee(user):
    """An Employee whose user_id is ``user`` (the driver-link chain anchor)."""
    name = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if name:
        return name
    doc = frappe.get_doc(
        {
            "doctype": "Employee",
            "employee_name": user.split("@")[0],
            "first_name": user.split("@")[0],
            "user_id": user,
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
        }
    )
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _driver(user, full_name):
    existing = frappe.db.get_value("Salis Driver", {"driver_user": user}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "full_name": full_name,
            "employee": _employee(user),
        }
    )
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _trip(driver):
    doc = frappe.get_doc(
        {"doctype": "Dispatch Trip", "driver": driver, "status": "Planned"}
    )
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)
    return doc.name


class TestDispatchTripDriverScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.user_a = _user("dtscope_driver_a@example.com", "Driver")
        cls.user_b = _user("dtscope_driver_b@example.com", "Driver")
        cls.driver_a = _driver(cls.user_a, "DT Scope Driver A")
        cls.driver_b = _driver(cls.user_b, "DT Scope Driver B")
        cls.trip_a = _trip(cls.driver_a)
        cls.trip_b = _trip(cls.driver_b)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for t in (cls.trip_a, cls.trip_b):
            frappe.delete_doc("Dispatch Trip", t, ignore_permissions=True, force=True)
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _trips_matching_query(self, user):
        """Names returned when the PQC fragment for ``user`` is run as a WHERE
        clause against tabDispatch Trip — i.e. exactly what the desk list scopes
        to, independent of the (absent) Driver desk DocPerm."""
        cond = dispatch_trip_query(user)
        sql = "select name from `tabDispatch Trip`"
        if cond:
            sql += " where " + cond
        return {r[0] for r in frappe.db.sql(sql)}

    def test_query_driver_a_sees_own_trip_only(self):
        names = self._trips_matching_query(self.user_a)
        self.assertIn(self.trip_a, names, "driver A must see their own trip")
        self.assertNotIn(
            self.trip_b, names, "driver A must NOT see driver B's trip via the PQC"
        )

    def test_query_driver_b_sees_own_trip_only(self):
        names = self._trips_matching_query(self.user_b)
        self.assertIn(self.trip_b, names)
        self.assertNotIn(self.trip_a, names)

    def test_has_permission_allows_own_denies_other(self):
        frappe.set_user(self.user_a)
        self.assertIsNone(
            dispatch_trip_has_permission(
                frappe.get_doc("Dispatch Trip", self.trip_a), "read", user=self.user_a
            ),
            "driver A may read their own trip",
        )
        self.assertFalse(
            dispatch_trip_has_permission(
                frappe.get_doc("Dispatch Trip", self.trip_b), "read", user=self.user_a
            ),
            "driver A must NOT read driver B's trip",
        )


if __name__ == "__main__":
    unittest.main()
