# Copyright (c) 2026, AFMCO and contributors
"""The driver portal resolves WHO is calling; the client never names a driver.

``profile.get_driver_profile`` and ``trips.my_trips_today`` both run
``_require_enabled()`` then ``_resolve_driver()``, so the record they answer with is
the caller's own or the call fails. These cases hold that from the outside: a second
driver reading the same endpoint gets their OWN row, a signed-in user with no linked
Salis Driver is refused rather than shown someone else's, and the portal switch in
Salis Settings closes both doors.

The trips case is written against a DISPATCHED trip on today's date because that is
the only shape ``my_trips_today`` selects — asserting the absence of a Planned trip
would pass whether or not the driver filter existed at all.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal
from apex.tests.factories import (
    make_driver_without_vehicle as _driver_without_vehicle,
    make_test_driver as _ensure_test_driver,
)


class TestDriverPortalIdentityScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver_a = _ensure_test_driver()
        cls.user_a = frappe.db.get_value(
            "Employee", frappe.db.get_value("Salis Driver", cls.driver_a, "employee"), "user_id"
        )
        cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    def _as(self, user, call, *args, **kwargs):
        frappe.set_user(user)
        try:
            return call(*args, **kwargs)
        finally:
            frappe.set_user("Administrator")

    def test_profile_returns_the_calling_driver(self):
        profile = self._as(self.user_a, driver_portal.get_driver_profile)
        self.assertEqual(profile["name"], self.driver_a)
        self.assertIn("full_name", profile)
        self.assertIn("license_expiry", profile)

    def test_a_second_driver_reads_their_own_row_not_the_first_one(self):
        """The client supplies no driver id, so the only thing that can change the
        answer is who is calling."""
        profile = self._as(self.user_b, driver_portal.get_driver_profile)
        self.assertEqual(profile["name"], self.driver_b)
        self.assertNotEqual(profile["name"], self.driver_a)

    def test_a_user_with_no_linked_driver_is_refused(self):
        outsider = "dp_scope_outsider@example.com"
        if not frappe.db.exists("User", outsider):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": outsider,
                    "first_name": "Outsider",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            self._as(outsider, driver_portal.get_driver_profile)

    def test_the_portal_switch_closes_the_profile(self):
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        self.addCleanup(
            frappe.db.set_single_value, "Salis Settings", "enable_driver_portal", 1
        )
        with self.assertRaises(frappe.PermissionError):
            self._as(self.user_a, driver_portal.get_driver_profile)

    def test_todays_trips_are_scoped_to_the_calling_driver(self):
        trip = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "driver": self.driver_a,
                "trip_date": frappe.utils.today(),
                "status": "Planned",
            }
        ).insert(ignore_permissions=True)
        # my_trips_today selects only Dispatched rows; the workflow that normally moves
        # a trip there is not the subject here, so the status is stamped directly.
        frappe.db.set_value("Dispatch Trip", trip.name, "status", "Dispatched")

        mine = [t["name"] for t in self._as(self.user_a, driver_portal.my_trips_today)]
        theirs = [t["name"] for t in self._as(self.user_b, driver_portal.my_trips_today)]

        self.assertIn(trip.name, mine)
        self.assertNotIn(trip.name, theirs)
