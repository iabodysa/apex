# Copyright (c) 2026, AFMCO and contributors
"""get_my_today composite-read tests: the single "today" payload the driver Home
screen paints from.

Covers the T-338 addition: get_my_today() returns the attendance state, the next
not-done trip (with its Trip Start Log state), the licence countdown, the
vehicle-bound flag, and the open-clearance flag in one identity-scoped read, and
403s a non-driver / a disabled portal.

Style matches the existing portal suites: FrappeTestCase (everything rolls back at
class teardown), no explicit frappe.db.commit(), and the driver helpers are reused.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal
from apex.tests.factories import make_test_driver as _ensure_test_driver
from apex.tests.factories import make_driver_without_vehicle as _driver_without_vehicle


class TestDriverPortalToday(FrappeTestCase):
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
		cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_returns_composite_shape_for_linked_driver(self):
		"""A linked driver gets the full composite — every section key present."""
		frappe.set_user(self.user_a)
		today = driver_portal.get_my_today()
		for key in ("attendance", "next_trip", "license", "vehicle_bound", "open_clearance"):
			self.assertIn(key, today)
		# [#p7g2th]
		self.assertIn("checked_in", today["attendance"])
		self.assertIn("checked_out", today["attendance"])
		# [#7svudf]
		self.assertTrue(today["vehicle_bound"])

	def test_rejects_non_driver(self):
		"""A logged-in user with no linked Salis Driver is rejected (PermissionError)."""
		outsider = "today_outsider@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc(
				{"doctype": "User", "email": outsider, "first_name": "Outsider",
				 "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			driver_portal.get_my_today()

	def test_blocked_when_portal_disabled(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
		try:
			frappe.set_user(self.user_a)
			with self.assertRaises(frappe.PermissionError):
				driver_portal.get_my_today()
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)

	def test_no_vehicle_driver_has_false_bound_flag(self):
		"""A driver with neither current_vehicle nor an Active Assignment reports
		vehicle_bound=False (a friendly, truthful flag, not an error)."""
		frappe.set_user(self.user_b)
		today = driver_portal.get_my_today()
		self.assertFalse(today["vehicle_bound"])

	def test_next_trip_surfaces_planned_trip_with_log_state(self):
		"""The next not-done trip today is returned with human labels and its Trip
		Start Log state; a Completed trip is excluded so 'next' stays actionable."""
		frappe.set_user("Administrator")
		# [#pvzwuu]
		done = frappe.get_doc(
			{"doctype": "Dispatch Trip", "driver": self.driver_a,
			 "trip_date": frappe.utils.today(), "depart_time": "06:00:00",
			 "status": "Planned"}
		).insert(ignore_permissions=True)
		done.db_set("status", "Completed")
		plan = frappe.get_doc(
			{"doctype": "Route Plan", "route_name": "Today Next Route",
			 "driver": self.driver_a, "vehicle": self.vehicle_a}
		).insert(ignore_permissions=True)
		nxt = frappe.get_doc(
			{"doctype": "Dispatch Trip", "driver": self.driver_a,
			 "trip_date": frappe.utils.today(), "depart_time": "08:00:00",
			 "route_plan": plan.name, "vehicle": self.vehicle_a, "status": "Planned"}
		).insert(ignore_permissions=True)
		log = frappe.get_doc(
			{"doctype": "Trip Start Log", "dispatch_trip": nxt.name, "status": "Started",
			 "start_datetime": frappe.utils.now_datetime()}
		)
		log.insert(ignore_permissions=True)
		log.submit()

		frappe.set_user(self.user_a)
		today = driver_portal.get_my_today()
		trip = today["next_trip"]
		self.assertIsNotNone(trip)
		self.assertEqual(trip["name"], nxt.name)
		self.assertEqual(trip["status"], "Planned")
		# [#5fqy9a]
		self.assertEqual(trip["route_plan"], "Today Next Route")
		self.assertEqual(trip["vehicle"], frappe.db.get_value(
			"Salis Vehicle", self.vehicle_a, "plate_number"))
		# [#jwi4kc]
		self.assertTrue(trip["started"])
		self.assertEqual(trip["trip_log_status"], "Started")

	def test_open_clearance_flag_reflects_unresolved_clearance(self):
		"""open_clearance is True while a Driver Clearance is Open/In Progress/Blocked
		and False once it is resolved (Cancelled here)."""
		frappe.set_user("Administrator")
		clearance = frappe.get_doc(
			{"doctype": "Driver Clearance", "driver": self.driver_b, "status": "Open"}
		).insert(ignore_permissions=True)

		frappe.set_user(self.user_b)
		self.assertTrue(driver_portal.get_my_today()["open_clearance"])

		frappe.set_user("Administrator")
		clearance.db_set("status", "Cancelled")
		frappe.set_user(self.user_b)
		self.assertFalse(driver_portal.get_my_today()["open_clearance"])

	def test_license_countdown_is_server_computed(self):
		"""The licence section carries a signed days_to_expiry and a state, so the SPA
		needs no date math: an expiry 10 days out is 'expiring' with days_to_expiry 10."""
		frappe.set_user("Administrator")
		future = frappe.utils.add_days(frappe.utils.today(), 10)
		frappe.db.set_value("Salis Driver", self.driver_a, "license_expiry", future)
		frappe.set_user(self.user_a)
		lic = driver_portal.get_my_today()["license"]
		self.assertEqual(lic["days_to_expiry"], 10)
		self.assertEqual(lic["state"], "expiring")
		self.assertEqual(lic["expiry_date"], str(future))
