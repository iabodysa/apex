# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal
from apex_habitat.salis.api.driver_portal import _resolve_driver

# NOTE: test_masar_worker_movement imports _ensure_test_driver from THIS module, so a
# top-level `from ... import` here would be circular. The worker-trip builder is therefore
# imported lazily inside the helper that needs it (below).


def _ensure_test_driver():
	"""Create a User+Employee+Salis Driver chain for portal tests; return driver name.

	Under FrappeTestCase every row created here lives inside the class transaction and
	is rolled back at class teardown, so the chain stays test-local (no dev-site
	pollution) and there is no cross-suite race that needs a DuplicateEntry guard."""
	user = "drv_dp@example.com"
	if not frappe.db.exists("User", user):
		try:
			u = frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "Test Driver", "send_welcome_email": 0}
			)
			u.add_roles("Driver")
			u.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			# [#1b2cml]
			pass
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

	def test_trips_show_human_labels_not_link_ids(self):
		"""my_trips_today returns plate / route name, not raw link ids (T-169)."""
		drv = _ensure_test_driver()
		veh_id = frappe.db.get_value("Salis Driver", drv, "current_vehicle")
		plate = frappe.db.get_value("Salis Vehicle", veh_id, "plate_number")
		rp = frappe.get_doc(
			{"doctype": "Route Plan", "route_name": "DP Test Route",
			 "driver": drv, "vehicle": veh_id}
		).insert(ignore_permissions=True)
		trips = [{"name": "T1", "vehicle": veh_id, "route_plan": rp.name}]
		driver_portal._label_trips(trips)
		self.assertEqual(trips[0]["vehicle"], plate)
		self.assertEqual(trips[0]["route_plan"], "DP Test Route")
		self.assertNotEqual(trips[0]["vehicle"], veh_id)

	def test_check_in_creates_attendance_for_self(self):
		drv, user = self._driver_user()
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		res = driver_portal.driver_check_in()
		self.assertTrue(frappe.db.exists("Driver Attendance", res["name"]))
		att = frappe.get_doc("Driver Attendance", res["name"])
		self.assertEqual(att.driver, drv)
		self.assertEqual(str(att.attendance_date), frappe.utils.today())
		# [#ej6tem]
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
		# [#5sak8a]
		self.assertEqual(frappe.db.get_value("Issue", tk["name"], "custom_driver"), drv)
		frappe.set_user("Administrator")

	def test_check_in_leaves_check_out_empty(self):
		"""T-537: a single check-in opens the shift and must NEVER stamp check-out.

		Frappe core fills every Time field with nowtime() on a brand-new doc
		(create_new.py set_dynamic_default_values), so without an explicit guard an
		inserted Driver Attendance inherited a phantom check_out == check_in (an
		instant zero-length "full day"). Check-in must leave check_out empty and the
		shift open."""
		drv, user = self._driver_user()
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		res = driver_portal.driver_check_in()
		# [#t537co] the projected state the SPA applies must show an OPEN shift
		self.assertTrue(res["checked_in"], "Check-in marks the driver present.")
		self.assertFalse(res["checked_out"], "Check-in must NOT mark checked out.")
		self.assertIsNone(res["check_out"], "Check-in must leave check_out empty.")
		# [#t537db] and the persisted row must agree (no phantom stamp on disk)
		frappe.set_user("Administrator")
		row = frappe.db.get_value(
			"Driver Attendance", res["name"], ["check_in", "check_out", "worked_hours"], as_dict=True
		)
		self.assertTrue(row.check_in, "check_in persisted.")
		self.assertFalse(row.check_out, "check_out must be empty on the persisted row.")
		self.assertEqual(row.worked_hours or 0, 0, "An open shift has no worked hours yet.")
		frappe.set_user("Administrator")

	def test_check_out_refuses_zero_length_day(self):
		"""T-537: a check-out at or before check-in is rejected with a friendly error
		rather than recording a zero-length shift."""
		drv, user = self._driver_user()
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		ci = driver_portal.driver_check_in()
		# Pin nowtime() to the check-in instant to simulate an immediate stray tap.
		import apex_habitat.salis.api.driver_portal as dp_mod

		original = dp_mod.frappe.utils.nowtime
		dp_mod.frappe.utils.nowtime = lambda: ci["check_in"][:8]
		try:
			with self.assertRaises(frappe.ValidationError):
				driver_portal.driver_check_out()
		finally:
			dp_mod.frappe.utils.nowtime = original
		# The shift stays open; no check_out was written.
		frappe.set_user("Administrator")
		self.assertFalse(
			frappe.db.get_value("Driver Attendance", ci["name"], "check_out"),
			"A rejected zero-length check-out must not stamp check_out.",
		)
		frappe.set_user("Administrator")

	def test_check_out_without_check_in_records_no_phantom(self):
		"""T-537: checking out with no prior check-in records presence as a check-out
		only — it must NOT fabricate a phantom check_in == check_out (zero-length day).
		Frappe core stamps every blank Time field at insert, so this guards the
		symmetric case of the check-in bug."""
		drv, user = self._driver_user()
		self._clear_today_attendance(drv)
		frappe.set_user(user)
		res = driver_portal.driver_check_out()
		self.assertTrue(res["checked_out"], "Check-out is recorded.")
		self.assertFalse(res["checked_in"], "No phantom check-in is created.")
		self.assertIsNone(res["check_in"], "check_in stays empty when never checked in.")
		frappe.set_user("Administrator")
		row = frappe.db.get_value(
			"Driver Attendance", res["name"], ["check_in", "check_out", "worked_hours"], as_dict=True
		)
		self.assertFalse(row.check_in, "No phantom check_in on the persisted row.")
		self.assertTrue(row.check_out, "check_out persisted.")
		self.assertEqual(row.worked_hours or 0, 0, "No fabricated worked hours.")
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
		# [#s10x5i]
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

		# [#fibtfn]
		self._purge()
		missing_attendance_watch()
		self.assertEqual(
			len(self._open_alerts()), 1,
			"A driver with no attendance must raise one Supervisor Delay alert.",
		)

		# [#98kf3q]
		frappe.set_user(self.user)
		res = driver_portal.driver_check_in()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Driver Attendance", res["name"], "docstatus"), 1,
			"Portal check-in must leave a SUBMITTED attendance for the watcher to see.",
		)

		# [#5z1fqj]
		reconcile_operations_alerts()
		self.assertEqual(
			self._open_alerts(), [],
			"An open Supervisor Delay alert must auto-resolve once the driver has "
			"checked in via the portal.",
		)

		# [#j27pvq]
		missing_attendance_watch()
		self.assertEqual(
			self._open_alerts(), [],
			"A driver who has checked in via the portal must raise no Supervisor "
			"Delay alert.",
		)


class _DriverTripBuilder:
	"""Builds a worker trip bound to the test driver via the proven Masar mixin,
	imported lazily to avoid the test_masar_worker_movement <-> test_driver_portal
	import cycle. Mix into a FrappeTestCase that sets ``self.drv``."""

	def _trip(self, workers, route):
		from apex_habitat.tests.test_masar_worker_movement import _WorkerTripMixin

		# _worker_trip uses self.addCleanup + self._purge; bind the mixin's _purge so
		# the cleanup it registers resolves on this (non-mixin) test case.
		self._purge = _WorkerTripMixin._purge
		_tr, _rp, dt = _WorkerTripMixin._worker_trip(self, self.drv, self.project, self.building, workers, route)
		# FrappeTestCase rolls back only at class end, so writes accumulate across the
		# methods in a class. _purge drops the trip/route/request but NOT the Trip Start
		# Log + Boarding Scan Log a board creates; clear those too so a reused dispatch-
		# trip name (the naming counter is not durably advanced inside the held class
		# transaction) can never inherit a prior method's open log / aboard worker.
		self.addCleanup(lambda name=dt.name: self._purge_trip_boarding(name))
		return dt

	@staticmethod
	def _purge_trip_boarding(dispatch_trip):
		frappe.set_user("Administrator")
		for log in frappe.get_all("Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"):
			frappe.delete_doc("Trip Start Log", log, ignore_permissions=True, force=True)
		for scan in frappe.get_all("Boarding Scan Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"):
			frappe.delete_doc("Boarding Scan Log", scan, ignore_permissions=True, force=True)


class TestManualBoarding(_DriverTripBuilder, FrappeTestCase):
	"""The no-scan fallback. A driver marks manifest workers aboard via
	manual_board_workers; the write must append a Trip Boarding Event (method
	Manual) and a Boarding Scan Log row, exactly as a QR scan does — and stay
	idempotent and manifest-scoped."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		from apex_habitat.tests.test_masar_worker_movement import _building, _employee, _project

		cls.drv = _ensure_test_driver()
		cls.user = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.drv, "employee"), "user_id"
		)
		cls.project = _project("Manual Board Project")
		cls.building = _building("Manual Board Building")
		cls.w1 = _employee("Manual Board One")
		cls.w2 = _employee("Manual Board Two")
		cls.off = _employee("Manual Board Off Manifest")

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _trip(self, route):
		return super()._trip([self.w1, self.w2], route)

	def test_manual_board_creates_boarding_and_audit_rows(self):
		"""The core goal: a manual board appends a Manual Trip Boarding Event and a
		Manual Boarding Scan Log row."""
		dt = self._trip("Manual Route A")
		frappe.set_user(self.user)
		res = driver_portal.manual_board_workers(dt.name, frappe.as_json([self.w1]))
		frappe.set_user("Administrator")

		self.assertEqual(res["boarded"], [self.w1])
		log = frappe.get_doc("Trip Start Log", res["trip_start_log"])
		self.assertEqual(log.boarded_count, 1)
		row = log.boarding_events[0]
		self.assertEqual(row.worker, self.w1)
		self.assertEqual(row.method, "Manual")
		# A Manual Boarding Scan Log audit row exists for this worker.
		scan = frappe.get_all(
			"Boarding Scan Log",
			filters={"dispatch_trip": dt.name, "worker": self.w1},
			fields=["result", "method", "boarding_event_created"],
		)
		self.assertEqual(len(scan), 1)
		self.assertEqual(scan[0]["result"], "Valid")
		self.assertEqual(scan[0]["method"], "Manual")
		self.assertEqual(scan[0]["boarding_event_created"], 1)

	def test_manual_board_is_idempotent(self):
		dt = self._trip("Manual Route B")
		frappe.set_user(self.user)
		first = driver_portal.manual_board_workers(dt.name, frappe.as_json([self.w1]))
		second = driver_portal.manual_board_workers(dt.name, frappe.as_json([self.w1]))
		frappe.set_user("Administrator")
		self.assertEqual(first["boarded"], [self.w1])
		self.assertEqual(second["boarded"], [])  # already aboard -> no second row
		self.assertEqual(second["skipped"][0]["result"], "Duplicate")
		log = frappe.get_doc("Trip Start Log", first["trip_start_log"])
		self.assertEqual(log.boarded_count, 1)

	def test_manual_board_rejects_off_manifest_worker(self):
		dt = self._trip("Manual Route C")
		frappe.set_user(self.user)
		res = driver_portal.manual_board_workers(dt.name, frappe.as_json([self.off]))
		frappe.set_user("Administrator")
		self.assertEqual(res["boarded"], [])
		self.assertEqual(res["skipped"][0]["result"], "Wrong Trip")

	def test_manual_boarding_sheet_marks_aboard(self):
		dt = self._trip("Manual Route D")
		frappe.set_user(self.user)
		driver_portal.manual_board_workers(dt.name, frappe.as_json([self.w1]))
		sheet = driver_portal.manual_boarding_sheet(dt.name)
		frappe.set_user("Administrator")
		by_emp = {w["employee"]: w for w in sheet["workers"]}
		self.assertTrue(by_emp[self.w1]["boarded"])
		self.assertFalse(by_emp[self.w2]["boarded"])
		self.assertEqual(sheet["boarded_count"], 1)


class TestStopProgress(_DriverTripBuilder, FrappeTestCase):
	"""Per-stop checkpoints persist on the trip's Trip Start Log and survive
	a reload (re-read)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
		from apex_habitat.tests.test_masar_worker_movement import _building, _employee, _project

		cls.drv = _ensure_test_driver()
		cls.user = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.drv, "employee"), "user_id"
		)
		cls.project = _project("Stop Progress Project")
		cls.building = _building("Stop Progress Building")
		cls.w1 = _employee("Stop Progress Worker")

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _trip(self, route):
		return super()._trip([self.w1], route)

	def test_mark_stop_requires_started_trip(self):
		dt = self._trip("Stop Route A")
		# my_trip_route is identity-scoped (driver resolved from the session), so it must
		# run as the driver — Administrator owns no trip and would get "Trip not found".
		frappe.set_user(self.user)
		route = driver_portal.my_trip_route(dt.name)
		stop = next(s for s in route["stops"] if s.get("route_stop"))
		# No Trip Start Log yet -> marking a stop must be refused.
		with self.assertRaises(frappe.ValidationError):
			driver_portal.mark_stop_progress(dt.name, stop["route_stop"], done=1)
		frappe.set_user("Administrator")

	def test_stop_progress_persists_and_survives_reload(self):
		dt = self._trip("Stop Route B")
		frappe.set_user(self.user)
		driver_portal.start_my_trip(dt.name)  # opens the Trip Start Log
		route = driver_portal.my_trip_route(dt.name)
		self.assertTrue(route["started"])
		stop = next(s for s in route["stops"] if s.get("route_stop"))
		self.assertFalse(stop["done"])

		res = driver_portal.mark_stop_progress(
			dt.name, stop["route_stop"], done=1, sequence=stop.get("sequence"),
			stop_name=stop.get("stop_name"),
		)
		self.assertTrue(res["stop_progress"][stop["route_stop"]]["done"])

		# Re-read (reload): the done-state must be reflected from the server.
		reloaded = driver_portal.my_trip_route(dt.name)
		frappe.set_user("Administrator")
		marked = next(s for s in reloaded["stops"] if s["route_stop"] == stop["route_stop"])
		self.assertTrue(marked["done"], "Stop done-state must survive a reload.")

		# It persisted as a Trip Stop Progress row on the open Trip Start Log.
		log_name = frappe.db.get_value(
			"Trip Start Log", {"dispatch_trip": dt.name, "docstatus": 0}, "name"
		)
		rows = frappe.get_all(
			"Trip Stop Progress",
			filters={"parent": log_name, "parenttype": "Trip Start Log", "done": 1},
			pluck="route_stop",
		)
		self.assertIn(stop["route_stop"], rows)

	def test_stop_can_be_unmarked(self):
		dt = self._trip("Stop Route C")
		frappe.set_user(self.user)
		driver_portal.start_my_trip(dt.name)
		route = driver_portal.my_trip_route(dt.name)
		stop = next(s for s in route["stops"] if s.get("route_stop"))
		driver_portal.mark_stop_progress(dt.name, stop["route_stop"], done=1)
		res = driver_portal.mark_stop_progress(dt.name, stop["route_stop"], done=0)
		frappe.set_user("Administrator")
		self.assertFalse(res["stop_progress"].get(stop["route_stop"], {}).get("done"))
