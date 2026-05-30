"""Driver-portal enrichment tests: the read-only, identity-scoped profile and
vehicle endpoints.

These cover the 1.20.0 additions:
  * get_driver_profile() returns ONLY the caller's own driver — a foreign driver
    cannot read another's profile (identity-scoped, resolved server-side).
  * get_my_vehicle() returns the bound vehicle, and a friendly empty state when
    the driver has none.
  * Both endpoints are blocked when the driver portal is disabled.

Style matches the existing portal suites: FrappeTestCase (everything rolls back at
class teardown), no explicit frappe.db.commit(), and the User+Employee+Salis Driver
helpers are reused from test_driver_portal / test_driver_portal_scope.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.test_driver_portal import _ensure_test_driver
from apex_habitat.tests.test_driver_portal_scope import _driver_without_vehicle


class TestDriverPortalProfile(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		# driver_a has a current_vehicle (set by the helper).
		cls.driver_a = _ensure_test_driver()
		cls.user_a = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.driver_a, "employee"), "user_id"
		)
		# driver_b is a different, vehicle-less driver.
		cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_profile_returns_own_driver(self):
		"""The profile is resolved from the session, so a driver gets their OWN row."""
		frappe.set_user(self.user_a)
		profile = driver_portal.get_driver_profile()
		self.assertEqual(profile["name"], self.driver_a)
		self.assertIn("full_name", profile)
		self.assertIn("license_expiry", profile)  # present (may be None), always JSON-safe

	def test_profile_is_identity_scoped_not_foreign(self):
		"""A foreign driver (driver_b) calling get_driver_profile() gets THEIR OWN
		row — never driver_a's. The client never supplies a driver id, so one driver
		cannot read another's profile."""
		frappe.set_user(self.user_b)
		profile = driver_portal.get_driver_profile()
		self.assertEqual(profile["name"], self.driver_b)
		self.assertNotEqual(profile["name"], self.driver_a)

	def test_profile_rejects_non_driver(self):
		"""A logged-in user with no linked Salis Driver is rejected (PermissionError)
		— the endpoint resolves a real driver before returning anything."""
		outsider = "enrich_outsider@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc(
				{"doctype": "User", "email": outsider, "first_name": "Outsider",
				 "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			driver_portal.get_driver_profile()

	def test_profile_blocked_when_portal_disabled(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
		try:
			frappe.set_user(self.user_a)
			with self.assertRaises(frappe.PermissionError):
				driver_portal.get_driver_profile()
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)


class TestDriverPortalVehicle(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		cls.driver_a = _ensure_test_driver()
		cls.user_a = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.driver_a, "employee"), "user_id"
		)
		cls.vehicle_a = frappe.db.get_value("Salis Driver", cls.driver_a, "current_vehicle")
		# A second driver with NO current_vehicle and no Active Vehicle Assignment.
		cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_vehicle_returns_bound_current_vehicle(self):
		"""A driver with a current_vehicle gets that vehicle's details."""
		frappe.set_user(self.user_a)
		res = driver_portal.get_my_vehicle()
		self.assertIsNotNone(res["vehicle"])
		self.assertEqual(res["vehicle"]["name"], self.vehicle_a)
		self.assertIn("plate_number", res["vehicle"])
		self.assertIn("assignment_start", res["vehicle"])

	def test_vehicle_friendly_empty_when_none(self):
		"""A driver with no bound vehicle gets a friendly empty payload, not an error."""
		frappe.set_user(self.user_b)
		res = driver_portal.get_my_vehicle()
		self.assertIsNone(res["vehicle"])

	def test_vehicle_resolves_via_active_assignment(self):
		"""When the driver has no current_vehicle but holds an Active Vehicle
		Assignment, that vehicle is returned (same binding rule as fuel writes),
		with the assignment start date surfaced."""
		frappe.set_user("Administrator")
		veh = frappe.get_doc(
			{"doctype": "Salis Vehicle", "plate_number": "ENRICH ASSIGN 1", "status": "Active"}
		).insert(ignore_permissions=True).name
		start = frappe.utils.today()
		frappe.get_doc(
			{"doctype": "Vehicle Assignment", "driver": self.driver_b, "vehicle": veh,
			 "status": "Active", "start_date": start}
		).insert(ignore_permissions=True)
		frappe.set_user(self.user_b)
		res = driver_portal.get_my_vehicle()
		self.assertIsNotNone(res["vehicle"])
		self.assertEqual(res["vehicle"]["name"], veh)
		self.assertEqual(res["vehicle"]["assignment_start"], str(start))

	def test_vehicle_blocked_when_portal_disabled(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
		try:
			frappe.set_user(self.user_a)
			with self.assertRaises(frappe.PermissionError):
				driver_portal.get_my_vehicle()
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
