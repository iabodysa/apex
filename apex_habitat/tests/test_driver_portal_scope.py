"""Driver portal identity-scope tests: a driver only sees their own data, and a
fuel request without an assigned vehicle is rejected."""

import unittest

import frappe

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.test_driver_portal import _ensure_test_driver


def _driver_without_vehicle(email):
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": "NoVeh",
                            "send_welcome_email": 0})
        u.add_roles("Driver")
        u.insert(ignore_permissions=True)
    emp = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if not emp:
        company = (frappe.defaults.get_global_default("company")
                   or frappe.get_all("Company", limit=1)[0].name)
        emp = frappe.get_doc({"doctype": "Employee", "first_name": "NoVeh", "user_id": email,
                              "date_of_birth": "1990-01-01", "date_of_joining": frappe.utils.today(),
                              "gender": "Male", "company": company}).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc({"doctype": "Salis Driver", "employee": emp,
                              "full_name": "NoVeh", "status": "Active"}).insert(
            ignore_permissions=True).name
    return drv, email


def _ensure_unlinked_user(email):
    """A logged-in user with NO Employee/Salis Driver chain — e.g. an admin
    previewing /driver. The portal must greet them, never 403."""
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Unlinked",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
    return email


class TestDriverPortalScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver_a = _ensure_test_driver()
        cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")
        cls.unlinked_user = _ensure_unlinked_user("drv_unlinked@example.com")
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_context_for_unlinked_user_is_friendly(self):
        """Regression (1.0.1): get_driver_context() for a user with no linked
        Salis Driver returns a friendly payload and does NOT raise."""
        frappe.set_user(self.unlinked_user)
        ctx = driver_portal.get_driver_context()
        self.assertEqual(ctx, {"enabled": True, "linked": False, "driver": None})

    def test_no_vehicle_blocks_fuel_request(self):
        frappe.set_user(self.user_b)
        with self.assertRaises(frappe.ValidationError):
            driver_portal.submit_fuel_request(litres=10)

    def test_trips_scoped_to_self(self):
        trip = frappe.get_doc({"doctype": "Dispatch Trip", "driver": self.driver_a,
                               "trip_date": frappe.utils.today(), "status": "Planned"}).insert(
            ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.user_b)
        names = [t["name"] for t in driver_portal.my_trips_today()]
        self.assertNotIn(trip.name, names)
        frappe.set_user("Administrator")
        trip.delete(ignore_permissions=True)
        frappe.db.commit()
