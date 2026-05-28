import unittest

import frappe

from apex_habitat.salis.api import driver_portal
from apex_habitat.salis.api.driver_portal import _resolve_driver


def _ensure_test_driver():
	"""Create a User+Employee+Salis Driver chain for portal tests; return driver name."""
	user = "drv_dp@example.com"
	if not frappe.db.exists("User", user):
		u = frappe.get_doc({"doctype": "User", "email": user, "first_name": "Test Driver",
		                    "send_welcome_email": 0})
		u.add_roles("Driver")
		u.insert(ignore_permissions=True)
	emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		company = (frappe.defaults.get_global_default("company")
		           or frappe.get_all("Company", limit=1)[0].name)
		emp = frappe.get_doc({"doctype": "Employee", "first_name": "Test Driver",
		                      "user_id": user, "date_of_birth": "1990-01-01",
		                      "date_of_joining": frappe.utils.today(), "gender": "Male",
		                      "company": company}).insert(ignore_permissions=True).name
	drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
	if not drv:
		drv = frappe.get_doc({"doctype": "Salis Driver", "employee": emp,
		                      "full_name": "Test Driver", "status": "Active"}).insert(
			ignore_permissions=True).name
	if not frappe.db.get_value("Salis Driver", drv, "current_vehicle"):
		veh = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "DP TEST 1",
		                      "status": "Active"}).insert(ignore_permissions=True).name
		frappe.db.set_value("Salis Driver", drv, "current_vehicle", veh)
	frappe.db.commit()
	return drv


class TestDriverPortal(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		cls.outsider = "outsider_dp@example.com"
		if not frappe.db.exists("User", cls.outsider):
			frappe.get_doc({"doctype": "User", "email": cls.outsider, "first_name": "Outsider",
			                "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.db.commit()

	def _driver_user(self):
		drv = _ensure_test_driver()
		emp = frappe.db.get_value("Salis Driver", drv, "employee")
		return drv, frappe.db.get_value("Employee", emp, "user_id")

	def test_resolve_driver_rejects_non_driver(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			_resolve_driver()
		frappe.set_user("Administrator")

	def test_reads_return_lists(self):
		drv, user = self._driver_user()
		frappe.set_user(user)
		self.assertIsInstance(driver_portal.my_trips_today(), list)
		self.assertIsInstance(driver_portal.my_support_tickets(), list)
		frappe.set_user("Administrator")

	def test_check_in_creates_attendance_for_self(self):
		drv, user = self._driver_user()
		frappe.set_user(user)
		res = driver_portal.driver_check_in()
		self.assertTrue(frappe.db.exists("Driver Attendance", res["name"]))
		att = frappe.get_doc("Driver Attendance", res["name"])
		self.assertEqual(att.driver, drv)
		self.assertEqual(str(att.attendance_date), frappe.utils.today())
		frappe.set_user("Administrator")
		att.delete(ignore_permissions=True)
		frappe.db.commit()

	def test_fuel_and_ticket_writes_scoped_to_self(self):
		drv, user = self._driver_user()
		frappe.set_user(user)
		fr = driver_portal.submit_fuel_request(litres=40)
		self.assertEqual(frappe.db.get_value("Fuel Request", fr["name"], "driver"), drv)
		self.assertEqual(frappe.db.get_value("Fuel Request", fr["name"], "status"), "Pending")
		tk = driver_portal.raise_support_ticket(category="Vehicle", priority="High",
		                                        subject="Brakes", description="Soft pedal")
		self.assertEqual(frappe.db.get_value("Support Ticket", tk["name"], "driver"), drv)
		frappe.set_user("Administrator")
