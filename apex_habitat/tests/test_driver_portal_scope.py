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


class TestDriverPortalScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver_a = _ensure_test_driver()
        cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

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
