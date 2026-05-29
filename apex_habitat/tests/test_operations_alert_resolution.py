"""Auto-resolution lifecycle for the Salis ``Operations Alert`` DocType.

The Salis engines RAISE Operations Alerts (licence expiry, idle vehicle, overdue
fuel request, attendance gap, excessive top-up). For a long time nothing CLOSED
them, so they accumulated as permanent noise. Resolution now happens two ways and
both are covered here:

* **Periodic** — ``reconcile_operations_alerts`` re-evaluates the live condition
  behind every open/acknowledged alert and flips the cleared ones to Resolved,
  stamping ``resolved_on`` + ``resolution_note``.
* **On source event** — reverting a temporary top-up resolves the open
  ``Excessive Topup`` alert for its vehicle immediately
  (``Fuel Request.on_update_after_submit`` -> ``resolve_excessive_topup_alerts``).

Each test drives a REAL watcher (or a real controller event) end to end: seed a
breach -> run -> alert Open; clear the breach -> run -> alert Resolved; and a
still-breaching entity must stay Open. Resolution must be idempotent (no
flip-flop, no duplicate) and must never delete an alert.
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_workflow_name
from frappe.utils import add_days, today

from apex_habitat.salis.tasks import (
	idle_vehicle_watch,
	missing_attendance_watch,
	reconcile_operations_alerts,
	unreverted_topup_watch,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _vehicle(plate, status="Active"):
	name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
	if not name:
		name = frappe.get_doc(
			{"doctype": "Salis Vehicle", "plate_number": plate, "status": status}
		).insert(ignore_permissions=True).name
	else:
		frappe.db.set_value("Salis Vehicle", name, "status", status)
	return name


def _driver(full_name, status="Active"):
	name = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
	if not name:
		name = frappe.get_doc(
			{"doctype": "Salis Driver", "full_name": full_name, "status": status}
		).insert(ignore_permissions=True).name
	else:
		frappe.db.set_value("Salis Driver", name, "status", status)
	return name


def _attendance(driver, when=None):
	when = when or today()
	if not frappe.db.exists(
		"Driver Attendance",
		{"driver": driver, "attendance_date": when, "docstatus": 1},
	):
		att = frappe.get_doc(
			{
				"doctype": "Driver Attendance",
				"driver": driver,
				"attendance_date": when,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()


def _drive_to_done(doc):
	"""Move a Pending Fuel Request to Done via the native workflow when active,
	else the direct save+submit fallback (mirrors test_fuel_request_unified)."""
	if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
		if doc.requested_by == frappe.session.user:
			doc.db_set("requested_by", "Guest")
			doc.reload()
		apply_workflow(doc, "Approve")
		doc.reload()
		apply_workflow(doc, "Complete")
		doc.reload()
	else:
		doc.status = "Approved"
		doc.save(ignore_permissions=True)
		doc.status = "Done"
		doc.save(ignore_permissions=True)
		doc.submit()


def _open_alerts(alert_type, **subject):
	"""Names of OPEN alerts of a type for a subject (vehicle/driver)."""
	return frappe.get_all(
		"Operations Alert",
		filters={"alert_type": alert_type, "status": "Open", **subject},
		pluck="name",
	)


def _purge_request(name):
	frappe.set_user("Administrator")
	if not frappe.db.exists("Fuel Request", name):
		return
	doc = frappe.get_doc("Fuel Request", name)
	if doc.docstatus == 1:
		try:
			doc.cancel()
		except Exception:
			pass
	frappe.delete_doc("Fuel Request", name, ignore_permissions=True, force=True)


def _purge_alerts(alert_type, **subject):
	frappe.set_user("Administrator")
	for n in frappe.get_all(
		"Operations Alert", filters={"alert_type": alert_type, **subject}, pluck="name"
	):
		frappe.delete_doc("Operations Alert", n, force=True, ignore_permissions=True)


def _purge_attendance(driver, when=None):
	"""Remove a driver's Driver Attendance (so an attendance-gap fixture genuinely
	starts with a gap). Submitted rows must be cancelled before deletion."""
	frappe.set_user("Administrator")
	filters = {"driver": driver}
	if when:
		filters["attendance_date"] = when
	for n in frappe.get_all("Driver Attendance", filters=filters, pluck="name"):
		doc = frappe.get_doc("Driver Attendance", n)
		if doc.docstatus == 1:
			try:
				doc.cancel()
			except Exception:
				pass
		frappe.delete_doc("Driver Attendance", n, force=True, ignore_permissions=True)


# ---------------------------------------------------------------------------
# Idle Vehicle — periodic raise -> clear -> resolve via real watcher
# ---------------------------------------------------------------------------


class TestIdleVehicleRaiseClearResolve(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		# A vehicle with NO recent trip -> idle_vehicle_watch raises an alert.
		cls.vehicle = _vehicle("OAR IDLE 1", status="Active")
		_purge_alerts("Idle Vehicle", vehicle=cls.vehicle)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_purge_alerts("Idle Vehicle", vehicle=cls.vehicle)
		frappe.db.commit()

	def test_raise_then_resolve_on_clear(self):
		# 1) breach -> watcher raises an Open Idle Vehicle alert.
		idle_vehicle_watch()
		frappe.db.commit()
		opened = _open_alerts("Idle Vehicle", vehicle=self.vehicle)
		self.assertEqual(len(opened), 1, "Idle vehicle must raise exactly one Open alert.")

		# 2) clear the condition: the vehicle is no longer Active.
		frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Stopped")
		frappe.db.commit()

		# 3) re-run the resolver -> alert auto-resolves, with resolved_on stamped.
		reconcile_operations_alerts()
		frappe.db.commit()

		alert = frappe.db.get_value(
			"Operations Alert",
			opened[0],
			["status", "resolved_on", "resolution_note"],
			as_dict=True,
		)
		self.assertEqual(alert.status, "Resolved", "Cleared idle vehicle must resolve.")
		self.assertIsNotNone(alert.resolved_on, "resolved_on must be stamped on resolution.")
		self.assertTrue(alert.resolution_note, "resolution_note must record the reason.")

		# 4) not duplicated and no new Open alert reappears for the same subject.
		self.assertEqual(
			_open_alerts("Idle Vehicle", vehicle=self.vehicle), [],
			"No Open Idle Vehicle alert should remain once the vehicle is inactive.",
		)

	def test_still_breaching_stays_open(self):
		# A different, still-Active vehicle with no trips stays breaching.
		v = _vehicle("OAR IDLE 2", status="Active")
		self.addCleanup(lambda: _purge_alerts("Idle Vehicle", vehicle=v))
		idle_vehicle_watch()
		frappe.db.commit()
		opened = _open_alerts("Idle Vehicle", vehicle=v)
		self.assertEqual(len(opened), 1)

		# Condition still holds (vehicle Active, still no trip) -> stays Open.
		reconcile_operations_alerts()
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Operations Alert", opened[0], "status"), "Open",
			"An alert whose condition still holds must stay Open.",
		)

	def test_resolution_is_idempotent(self):
		frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Active")
		_purge_alerts("Idle Vehicle", vehicle=self.vehicle)
		idle_vehicle_watch()
		frappe.db.commit()
		[name] = _open_alerts("Idle Vehicle", vehicle=self.vehicle)

		frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Stopped")
		frappe.db.commit()

		reconcile_operations_alerts()
		frappe.db.commit()
		first = frappe.db.get_value(
			"Operations Alert", name, ["status", "resolved_on"], as_dict=True
		)
		self.assertEqual(first.status, "Resolved")

		# Re-run: must not error, must not flip-flop, must not re-stamp resolved_on.
		reconcile_operations_alerts()
		frappe.db.commit()
		second = frappe.db.get_value(
			"Operations Alert", name, ["status", "resolved_on"], as_dict=True
		)
		self.assertEqual(second.status, "Resolved")
		self.assertEqual(
			str(first.resolved_on), str(second.resolved_on),
			"A re-run must not rewrite resolved_on on an already-Resolved alert.",
		)


# ---------------------------------------------------------------------------
# Supervisor Delay — attendance gap raise -> record attendance -> resolve
# ---------------------------------------------------------------------------


class TestAttendanceGapResolve(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.driver = _driver("OAR Gap Driver", status="Active")
		# Start from a genuine gap: clear any residual attendance/alerts (a prior
		# run records attendance to drive the resolve, so this guards re-runs).
		_purge_attendance(cls.driver)
		_purge_alerts("Supervisor Delay", driver=cls.driver)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		_purge_attendance(cls.driver)
		_purge_alerts("Supervisor Delay", driver=cls.driver)
		frappe.db.commit()

	def test_attendance_gap_resolves_when_attendance_recorded(self):
		missing_attendance_watch()
		frappe.db.commit()
		opened = _open_alerts("Supervisor Delay", driver=self.driver)
		self.assertEqual(len(opened), 1, "A missing-attendance driver must raise one alert.")

		# Resolver before attendance: condition still holds -> stays Open.
		reconcile_operations_alerts()
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Operations Alert", opened[0], "status"), "Open"
		)

		# Record attendance for the day the alert was raised -> clears.
		_attendance(self.driver)
		frappe.db.commit()
		reconcile_operations_alerts()
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Operations Alert", opened[0], "status"), "Resolved",
			"Recorded attendance must resolve the Supervisor Delay alert.",
		)


# ---------------------------------------------------------------------------
# Excessive Topup — resolve immediately on the revert source event
# ---------------------------------------------------------------------------


class TestExcessiveTopupResolveOnRevert(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.vehicle = _vehicle("OAR TOPUP 1", status="Active")
		frappe.db.commit()

	def _raise_excessive(self):
		a = frappe.get_doc(
			{
				"doctype": "Operations Alert",
				"alert_type": "Excessive Topup",
				"severity": "Critical",
				"status": "Open",
				"raised_on": frappe.utils.now_datetime(),
				"vehicle": self.vehicle,
				"message": "test excessive topup",
			}
		).insert(ignore_permissions=True)
		return a.name

	def test_revert_event_resolves_open_excessive_topup_alert(self):
		# A temporary top-up, driven to Done, with an open Excessive Topup alert.
		doc = frappe.get_doc(
			{
				"doctype": "Fuel Request",
				"request_type": "Top-up",
				"vehicle": self.vehicle,
				"topup_litres": 15,
				"is_temporary": 1,
				"revert_due_date": add_days(today(), 3),
				"status": "Pending",
			}
		)
		doc.insert(ignore_permissions=True)
		_drive_to_done(doc)
		frappe.db.commit()
		name = doc.name
		alert = self._raise_excessive()
		self.addCleanup(lambda: _purge_request(name))
		self.addCleanup(lambda: _purge_alerts("Excessive Topup", vehicle=self.vehicle))
		frappe.db.commit()

		self.assertEqual(frappe.db.get_value("Operations Alert", alert, "status"), "Open")

		# Source event: revert the top-up. The controller hook must resolve it.
		doc.reload()
		doc.reverted = 1
		doc.status = "Reverted"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		row = frappe.db.get_value(
			"Operations Alert", alert, ["status", "resolved_on"], as_dict=True
		)
		self.assertEqual(
			row.status, "Resolved",
			"Reverting a temporary top-up must resolve its Excessive Topup alert.",
		)
		self.assertIsNotNone(row.resolved_on)

	def test_revert_event_is_a_noop_without_matching_alert(self):
		# Reverting with no open alert for the vehicle must not error or create one.
		doc = frappe.get_doc(
			{
				"doctype": "Fuel Request",
				"request_type": "Top-up",
				"vehicle": self.vehicle,
				"topup_litres": 8,
				"is_temporary": 1,
				"revert_due_date": add_days(today(), 3),
				"status": "Pending",
			}
		)
		doc.insert(ignore_permissions=True)
		_drive_to_done(doc)
		frappe.db.commit()
		name = doc.name
		self.addCleanup(lambda: _purge_request(name))
		self.addCleanup(lambda: _purge_alerts("Excessive Topup", vehicle=self.vehicle))

		doc.reload()
		doc.reverted = 1
		doc.status = "Reverted"
		doc.save(ignore_permissions=True)  # must not raise
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Fuel Request", name, "status"), "Reverted"
		)


# ---------------------------------------------------------------------------
# Excessive Topup — periodic resolver clears the overdue-top-up source
# ---------------------------------------------------------------------------


class TestExcessiveTopupPeriodicResolve(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.vehicle = _vehicle("OAR TOPUP 2", status="Active")
		frappe.db.commit()

	def tearDown(self):
		_purge_alerts("Excessive Topup", vehicle=self.vehicle)
		frappe.db.commit()

	def test_periodic_resolver_keeps_open_while_overdue_topup_breaches(self):
		# Overdue unreverted temporary top-up -> Excessive Topup source breaches.
		doc = frappe.get_doc(
			{
				"doctype": "Fuel Request",
				"request_type": "Top-up",
				"vehicle": self.vehicle,
				"topup_litres": 20,
				"is_temporary": 1,
				"revert_due_date": add_days(today(), -3),
				"status": "Pending",
			}
		)
		doc.insert(ignore_permissions=True)
		_drive_to_done(doc)
		frappe.db.commit()
		name = doc.name
		self.addCleanup(lambda: _purge_request(name))

		# Raise an Excessive Topup alert as the monthly engine would.
		alert = frappe.get_doc(
			{
				"doctype": "Operations Alert",
				"alert_type": "Excessive Topup",
				"severity": "Critical",
				"status": "Open",
				"raised_on": frappe.utils.now_datetime(),
				"vehicle": self.vehicle,
				"message": "overage",
			}
		).insert(ignore_permissions=True).name
		frappe.db.commit()

		# While the overdue top-up is still unreverted, the source still breaches
		# -> the periodic resolver must NOT close the alert.
		reconcile_operations_alerts()
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Operations Alert", alert, "status"), "Open",
			"Excessive Topup must stay Open while an overdue top-up is unreverted.",
		)

		# Clear the source via the real watcher (it reverts the overdue top-up).
		unreverted_topup_watch()
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Fuel Request", name, "reverted"), 1)

		# Now the periodic resolver clears the (pre-existing) alert. The watcher
		# may have raised its own fresh notice; both must end Resolved once the
		# source is clear, so no Open Excessive Topup remains for the vehicle.
		reconcile_operations_alerts()
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("Operations Alert", alert, "status"), "Resolved",
			"Once the overdue top-up is reverted the Excessive Topup alert resolves.",
		)
		self.assertEqual(
			_open_alerts("Excessive Topup", vehicle=self.vehicle), [],
			"No Open Excessive Topup alert should remain once the source is clear.",
		)
