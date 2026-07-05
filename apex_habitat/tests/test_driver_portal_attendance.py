# Copyright (c) 2026, AFMCO and contributors
"""my_attendance(month) read tests: the driver's own month attendance history.

my_attendance() returns the caller's own Driver Attendance rows for a month
(default = current month), scoped strictly to the session driver, with
stringified times — and 403s a non-driver / a disabled portal.

Style matches the existing portal suites: FrappeTestCase (everything rolls back at
class teardown), no explicit frappe.db.commit(), and the driver helpers are reused.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.factories import make_test_driver as _ensure_test_driver
from apex_habitat.tests.factories import make_driver_without_vehicle as _driver_without_vehicle


def _attendance(driver, date, status="Present", check_in="08:00:00", check_out="17:00:00"):
	"""Insert+submit one Driver Attendance for a driver/date (test data only).

	A None time must persist as blank: Frappe core phantom-fills every empty Time
	field with nowtime() at insert (create_new.py set_dynamic_default_values), so a
	bare None would still land a value. Exclude the blank Time fields from
	update_if_missing — the same technique the portal controller uses — so the row
	on disk genuinely has no check-in/out when the test asks for one."""
	doc = frappe.get_doc(
		{
			"doctype": "Driver Attendance",
			"driver": driver,
			"attendance_date": date,
			"status": status,
			"check_in": check_in,
			"check_out": check_out,
		}
	)
	for field in ("check_in", "check_out"):
		if not doc.get(field) and field not in doc.dont_update_if_missing:
			doc.dont_update_if_missing.append(field)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


class TestDriverPortalAttendanceHistory(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		cls.driver_a = _ensure_test_driver()
		cls.user_a = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.driver_a, "employee"), "user_id"
		)
		cls.driver_b, cls.user_b = _driver_without_vehicle("drv_att_b@example.com")

		# Two days this month + one day last month for driver A.
		this_first = frappe.utils.get_first_day(frappe.utils.getdate())
		cls.this_month = frappe.utils.cstr(this_first)[:7]
		cls.day_1 = frappe.utils.cstr(this_first)
		cls.day_2 = frappe.utils.add_days(cls.day_1, 1)
		last_first = frappe.utils.get_first_day(frappe.utils.add_months(this_first, -1))
		cls.last_month = frappe.utils.cstr(last_first)[:7]
		cls.last_day = frappe.utils.cstr(last_first)

		_attendance(cls.driver_a, cls.day_1, status="Present")
		_attendance(cls.driver_a, cls.day_2, status="Late", check_out=None)
		_attendance(cls.driver_a, cls.last_day, status="Present")
		# A row for driver B this month — must never leak into driver A's history.
		_attendance(cls.driver_b, cls.day_1, status="Absent", check_in=None, check_out=None)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_returns_only_current_month_rows_by_default(self):
		"""No month arg -> the current month, newest day first, this-month rows only."""
		frappe.set_user(self.user_a)
		res = driver_portal.my_attendance()
		self.assertEqual(res["month"], self.this_month)
		dates = [r["attendance_date"] for r in res["rows"]]
		self.assertIn(self.day_1, dates)
		self.assertIn(self.day_2, dates)
		self.assertNotIn(self.last_day, dates)
		# newest-first ordering
		self.assertEqual(dates, sorted(dates, reverse=True))

	def test_month_arg_selects_that_month(self):
		"""An explicit YYYY-MM returns that month's rows (last month here)."""
		frappe.set_user(self.user_a)
		res = driver_portal.my_attendance(month=self.last_month)
		self.assertEqual(res["month"], self.last_month)
		dates = [r["attendance_date"] for r in res["rows"]]
		self.assertEqual(dates, [self.last_day])

	def test_scoped_to_self_never_leaks_another_driver(self):
		"""Driver A's history never contains driver B's row, even same month/day."""
		frappe.set_user(self.user_a)
		res = driver_portal.my_attendance()
		statuses = {r["status"] for r in res["rows"]}
		self.assertNotIn("Absent", statuses)  # B's row is the only Absent one
		frappe.set_user(self.user_b)
		res_b = driver_portal.my_attendance()
		self.assertEqual([r["status"] for r in res_b["rows"]], ["Absent"])

	def test_times_are_stringified_and_blanks_are_none(self):
		"""Time fields serialize as strings; a missing check-out comes back as None."""
		frappe.set_user(self.user_a)
		rows = {r["attendance_date"]: r for r in driver_portal.my_attendance()["rows"]}
		self.assertIsInstance(rows[self.day_1]["check_in"], str)
		self.assertIsInstance(rows[self.day_1]["check_out"], str)
		self.assertIsNone(rows[self.day_2]["check_out"])

	def test_blank_month_falls_back_to_current(self):
		"""A malformed/blank month never raises — it degrades to the current month."""
		frappe.set_user(self.user_a)
		self.assertEqual(driver_portal.my_attendance(month="not-a-month")["month"], self.this_month)

	def test_rejects_non_driver(self):
		outsider = "att_outsider@example.com"
		if not frappe.db.exists("User", outsider):
			frappe.get_doc(
				{"doctype": "User", "email": outsider, "first_name": "Outsider",
				 "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			driver_portal.my_attendance()

	def test_blocked_when_portal_disabled(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
		try:
			frappe.set_user(self.user_a)
			with self.assertRaises(frappe.PermissionError):
				driver_portal.my_attendance()
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
