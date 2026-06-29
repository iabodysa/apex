# Copyright (c) 2026, AFMCO and contributors
"""Action API for the Salis ``Operations Alert`` queue (salis/api/operations_alerts.py).

The operations-control board and the /fleet alert drawer read the open queue and
advance the status ladder. Three properties must hold and were previously
untested (test_operations_alert_resolution covers the periodic/event auto-resolver
only, never the manual board actions or the queue reader):

  1. Each action produces the CORRECT effect: acknowledge moves Open ->
     Acknowledged, resolve moves it to Resolved stamping resolved_on +
     resolution_note (reusing the shared _resolve_alert helper).
  2. Both actions are idempotent: a second call is a no-op and never flip-flops the
     status or rewrites the resolution timestamp.
  3. The reads/writes are permission-gated: a read-only role (Internal Auditor) is
     refused both writes, and get_open_alerts is project-scoped so a scoped Fleet
     Supervisor only sees alerts anchored to a vehicle in a permitted project.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api.operations_alerts import (
	AGING_DEFAULT,
	AGING_SETTING,
	_aging_thresholds,
	acknowledge_alert,
	get_open_alerts,
	resolve_alert,
)
from apex_habitat.tests._helpers import _user


def _vehicle(plate, project=None):
	name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
	if not name:
		name = frappe.get_doc(
			{"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active", "project": project}
		).insert(ignore_permissions=True).name
	elif project is not None:
		frappe.db.set_value("Salis Vehicle", name, "project", project)
	return name


def _project(name):
	p = frappe.db.get_value("Project", {"project_name": name}, "name")
	if not p:
		p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(ignore_permissions=True).name
	return p


def _alert(alert_type="Idle Vehicle", severity="Warning", vehicle=None):
	return frappe.get_doc(
		{
			"doctype": "Operations Alert",
			"alert_type": alert_type,
			"severity": severity,
			"status": "Open",
			"raised_on": frappe.utils.now_datetime(),
			"vehicle": vehicle,
			"message": "test alert action",
		}
	).insert(ignore_permissions=True).name


def _purge_alert(name):
	frappe.set_user("Administrator")
	if frappe.db.exists("Operations Alert", name):
		frappe.delete_doc("Operations Alert", name, force=True, ignore_permissions=True)


class TestOperationsAlertActions(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_acknowledge_moves_open_to_acknowledged(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		res = acknowledge_alert(name)
		self.assertTrue(res.get("acknowledged"))
		self.assertEqual(res.get("status"), "Acknowledged")
		self.assertEqual(frappe.db.get_value("Operations Alert", name, "status"), "Acknowledged")

	def test_acknowledge_is_idempotent(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		acknowledge_alert(name)
		# A second call must not flip-flop or report a fresh acknowledgement.
		again = acknowledge_alert(name)
		self.assertFalse(again.get("acknowledged"))
		self.assertEqual(frappe.db.get_value("Operations Alert", name, "status"), "Acknowledged")

	def test_resolve_stamps_resolution(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		res = resolve_alert(name, note="cleared on site")
		self.assertTrue(res.get("resolved"))
		row = frappe.db.get_value(
			"Operations Alert", name, ["status", "resolved_on", "resolution_note"], as_dict=True
		)
		self.assertEqual(row.status, "Resolved")
		self.assertIsNotNone(row.resolved_on, "resolved_on must be stamped on manual resolve")
		self.assertTrue(row.resolution_note, "resolution_note must record the reason")

	def test_resolve_is_idempotent(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		first = resolve_alert(name, note="first")
		self.assertTrue(first.get("resolved"))
		first_on = frappe.db.get_value("Operations Alert", name, "resolved_on")
		# A re-run must report resolved=False and must not rewrite resolved_on.
		second = resolve_alert(name, note="second")
		self.assertFalse(second.get("resolved"))
		self.assertEqual(
			str(first_on), str(frappe.db.get_value("Operations Alert", name, "resolved_on"))
		)

	def test_acknowledge_then_resolve(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		acknowledge_alert(name)
		resolve_alert(name)
		self.assertEqual(frappe.db.get_value("Operations Alert", name, "status"), "Resolved")

	def test_writes_gated_on_alert_write(self):
		name = _alert()
		self.addCleanup(lambda: _purge_alert(name))
		# Internal Auditor reads Operations Alert but cannot write it.
		auditor = _user("oa-actions-auditor@example.com", "Internal Auditor")
		frappe.set_user(auditor)
		with self.assertRaises(frappe.PermissionError):
			acknowledge_alert(name)
		with self.assertRaises(frappe.PermissionError):
			resolve_alert(name)


class TestOpenAlertsQueueScope(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.pa = _project("OA Scope A")
		cls.pb = _project("OA Scope B")
		cls.va = _vehicle("OA SCOPE A1", project=cls.pa)
		cls.vb = _vehicle("OA SCOPE B1", project=cls.pb)
		cls.sup = _user("oa-scope-sup@example.com", "Fleet Supervisor")
		if not frappe.db.exists(
			"User Permission", {"allow": "Project", "for_value": cls.pa, "user": cls.sup}
		):
			frappe.get_doc(
				{"doctype": "User Permission", "allow": "Project", "for_value": cls.pa, "user": cls.sup}
			).insert(ignore_permissions=True)
		cls.aa = _alert(vehicle=cls.va)
		cls.ab = _alert(vehicle=cls.vb)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		_purge_alert(cls.aa)
		_purge_alert(cls.ab)
		# setUpClass also commits Projects + Vehicles + a User Permission OUTSIDE
		# the per-method savepoint rollback; delete them so the @example.com
		# Project User Permission rows do not poison later tests on the bench.
		frappe.db.delete("User Permission",
			{"allow": "Project", "for_value": cls.pa, "user": cls.sup})
		for v in (cls.va, cls.vb):
			if frappe.db.exists("Salis Vehicle", v):
				frappe.delete_doc("Salis Vehicle", v, ignore_permissions=True, force=True)
		for p in (cls.pa, cls.pb):
			if frappe.db.exists("Project", p):
				frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
		frappe.db.commit()
		super().tearDownClass()

	def test_supervisor_sees_only_in_scope_alerts(self):
		frappe.set_user(self.sup)
		try:
			names = {a["name"] for a in get_open_alerts()["alerts"]}
		finally:
			frappe.set_user("Administrator")
		self.assertIn(self.aa, names, "scoped supervisor must see their own project's alert")
		self.assertNotIn(self.ab, names, "scoped supervisor must NOT see another project's alert")

	def test_oversight_sees_both(self):
		mgr = _user("oa-scope-mgr@example.com", "Fleet Manager")
		frappe.set_user(mgr)
		try:
			names = {a["name"] for a in get_open_alerts()["alerts"]}
		finally:
			frappe.set_user("Administrator")
		self.assertIn(self.aa, names)
		self.assertIn(self.ab, names, "an oversight role sees every project's alerts")


class TestAlertAgingThresholds(FrappeTestCase):
	"""The per-severity aging cutoffs the queue reads must come from real, defined
	Salis Settings fields (they were referenced in code but missing on the DocType),
	and must survive the Single new-field trap — a never-set or zeroed Int on a
	Single stores 0, so the reader must fall back to the built-in default.
	"""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		# Restore the persisted Single so a mutated value can't leak into other tests.
		frappe.set_user("Administrator")
		for field in AGING_SETTING.values():
			frappe.db.set_single_value("Salis Settings", field, 0)

	def test_aging_fields_defined_on_doctype(self):
		# Each referenced fieldname must be a real Int field on the Salis Settings meta.
		meta = frappe.get_meta("Salis Settings")
		for field in AGING_SETTING.values():
			df = meta.get_field(field)
			self.assertIsNotNone(df, f"{field} must be a defined field on Salis Settings")
			self.assertEqual(df.fieldtype, "Int", f"{field} must be an Int")

	def test_falls_back_to_default_when_unset_or_zero(self):
		# Single new-field trap: 0/unset must yield the built-in default, not 0 hours.
		for field in AGING_SETTING.values():
			frappe.db.set_single_value("Salis Settings", field, 0)
		self.assertEqual(_aging_thresholds(), AGING_DEFAULT)

	def test_reads_configured_value_when_set(self):
		# A non-zero stored value overrides the default for that severity.
		frappe.db.set_single_value("Salis Settings", AGING_SETTING["Warning"], 12)
		thresholds = _aging_thresholds()
		self.assertEqual(thresholds["Warning"], 12, "configured value must be read through")
		self.assertEqual(
			thresholds["Critical"], AGING_DEFAULT["Critical"], "unset severities keep the default"
		)
