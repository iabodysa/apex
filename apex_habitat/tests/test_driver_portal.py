import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal
from apex_habitat.salis.api.driver_portal import _resolve_driver


def _ensure_test_driver():
	"""Create a User+Employee+Salis Driver chain for portal tests; return driver name.

	Under FrappeTestCase every row created here lives inside the class transaction and
	is rolled back at class teardown, so the chain stays test-local (no dev-site
	pollution) and there is no cross-suite race that needs a DuplicateEntry guard."""
	user = "drv_dp@example.com"
	if not frappe.db.exists("User", user):
		u = frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "Test Driver", "send_welcome_email": 0}
		)
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
	return drv


class TestDriverPortal(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		cls.outsider = "outsider_dp@example.com"
		if not frappe.db.exists("User", cls.outsider):
			frappe.get_doc({"doctype": "User", "email": cls.outsider, "first_name": "Outsider",
			                "send_welcome_email": 0}).insert(ignore_permissions=True)

	def _driver_user(self):
		drv = _ensure_test_driver()
		emp = frappe.db.get_value("Salis Driver", drv, "employee")
		return drv, frappe.db.get_value("Employee", emp, "user_id")

	def _clear_today_attendance(self, driver):
		"""Drop any of today's Driver Attendance for ``driver`` so each attendance
		test starts from a clean slate. FrappeTestCase rolls back only at class
		teardown, not between methods, so a submitted check-in left by an earlier
		method would otherwise be re-touched here (``check_in`` is not
		allow_on_submit) and raise UpdateAfterSubmitError. This is the only
		inter-method cleanup these tests rely on; the class rollback handles the
		rest, so no commit is issued."""
		frappe.set_user("Administrator")
		for n in frappe.get_all(
			"Driver Attendance",
			filters={"driver": driver, "attendance_date": frappe.utils.today()},
			pluck="name",
		):
			doc = frappe.get_doc("Driver Attendance", n)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Driver Attendance", n, force=True, ignore_permissions=True)

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
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		res = driver_portal.driver_check_in()
		self.assertTrue(frappe.db.exists("Driver Attendance", res["name"]))
		att = frappe.get_doc("Driver Attendance", res["name"])
		self.assertEqual(att.driver, drv)
		self.assertEqual(str(att.attendance_date), frappe.utils.today())
		# A portal check-in is an authoritative presence record: it is SUBMITTED,
		# not left in draft, so the attendance watcher (which keys on docstatus=1)
		# recognises it and raises no perpetual Supervisor Delay alert.
		self.assertEqual(att.docstatus, 1, "Portal check-in must submit the attendance.")
		frappe.set_user("Administrator")

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

	def test_check_out_updates_submitted_record(self):
		"""Check-out stamps the SUBMITTED record (check_out / worked_hours are
		allow_on_submit), so a full in->out day stays one submitted attendance with
		computed hours — no draft, no second row."""
		drv, user = self._driver_user()
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		ci = driver_portal.driver_check_in()
		co = driver_portal.driver_check_out()
		self.assertEqual(ci["name"], co["name"], "Check-out must reuse the check-in record.")
		att = frappe.get_doc("Driver Attendance", co["name"])
		self.assertEqual(att.docstatus, 1, "Record stays submitted after check-out.")
		self.assertTrue(att.check_in and att.check_out, "Both times persisted on the submitted row.")
		frappe.set_user("Administrator")


class TestPortalCheckInNoPerpetualAlert(FrappeTestCase):
	"""F-02 regression: a driver who checks in through the mobile portal must NOT be
	left with a perpetual, unresolvable "Supervisor Delay" Operations Alert.

	Root cause: the portal saved Driver Attendance as a DRAFT (docstatus 0), but
	``missing_attendance_watch`` and the Supervisor-Delay branch of
	``reconcile_operations_alerts`` both require a SUBMITTED (docstatus 1) row. So a
	compliant portal user tripped a fresh alert every day that never auto-resolved.
	The fix submits the attendance on check-in. This test proves both halves:

	  1) after a portal check-in, the watcher raises NO alert for that driver; and
	  2) a Supervisor Delay alert already open for that driver auto-resolves once
	     the driver has checked in (the reconcile pass sees the submitted record).
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		cls.drv = _ensure_test_driver()
		# Driver must be Active for missing_attendance_watch to consider it.
		frappe.db.set_value("Salis Driver", cls.drv, "status", "Active")
		cls.user = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.drv, "employee"), "user_id"
		)
		cls._purge(cls)

	def _purge(self):
		frappe.set_user("Administrator")
		for n in frappe.get_all("Operations Alert",
		                        filters={"alert_type": "Supervisor Delay", "driver": self.drv},
		                        pluck="name"):
			frappe.delete_doc("Operations Alert", n, force=True, ignore_permissions=True)
		for n in frappe.get_all("Driver Attendance",
		                        filters={"driver": self.drv, "attendance_date": frappe.utils.today()},
		                        pluck="name"):
			doc = frappe.get_doc("Driver Attendance", n)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Driver Attendance", n, force=True, ignore_permissions=True)

	def _open_alerts(self):
		return frappe.get_all("Operations Alert",
		                      filters={"alert_type": "Supervisor Delay", "status": "Open",
		                               "driver": self.drv}, pluck="name")

	def test_portal_check_in_raises_no_alert_and_resolves_existing(self):
		from apex_habitat.salis.tasks import (
			missing_attendance_watch,
			reconcile_operations_alerts,
		)

		# Baseline: genuine gap -> watcher raises exactly one Supervisor Delay alert.
		self._purge()
		missing_attendance_watch()
		self.assertEqual(
			len(self._open_alerts()), 1,
			"A driver with no attendance must raise one Supervisor Delay alert.",
		)

		# Driver checks in through the portal (resolves to self server-side).
		frappe.set_user(self.user)
		res = driver_portal.driver_check_in()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Driver Attendance", res["name"], "docstatus"), 1,
			"Portal check-in must leave a SUBMITTED attendance for the watcher to see.",
		)

		# (1) The reconcile pass now sees a submitted attendance for the day the
		#     alert was raised and resolves the previously-perpetual alert.
		reconcile_operations_alerts()
		self.assertEqual(
			self._open_alerts(), [],
			"An open Supervisor Delay alert must auto-resolve once the driver has "
			"checked in via the portal.",
		)

		# (2) Re-running the watcher after the check-in raises NO new alert — the
		#     compliant portal user no longer floods a fresh alert each day.
		missing_attendance_watch()
		self.assertEqual(
			self._open_alerts(), [],
			"A driver who has checked in via the portal must raise no Supervisor "
			"Delay alert.",
		)
