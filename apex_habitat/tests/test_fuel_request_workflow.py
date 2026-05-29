"""Native Workflow tests for Fuel Request (Workflow Spine).

These lock in the conversion of the unified Fuel Request from a hand-rolled
status machine (the old ``_TRANSITIONS`` map) to the native **Fuel Request
Workflow**, and prove the behaviours the workflow now owns plus the side-effects
the controller still owns:

  * the workflow is seeded and active for Fuel Request;
  * a **post-submit transition is reachable** for every request_type:
    Pending -> Approved (submit, docstatus 0 -> 1) -> Done (docstatus 1) — the
    frozen-post-submit bug being fixed;
  * Segregation of Duties — the (server-stamped) requester cannot approve their
    own request (the approval transition is ``allow_self_approval=0`` and carries
    ``requested_by != session.user``); a different approver can;
  * type-aware transitions — ``Revert`` is offered only for a Top-up and
    ``Mark Failed`` only for a Standard request (the transition ``condition``s);
  * the Standard quota side-effect still fires when the request *reaches* Done
    via the post-submit workflow transition (the controller's
    ``on_update_after_submit``), idempotently — the whole point of the move.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Fuel Request is project-scoped, so
scoped approver roles are granted a Project User Permission in setUp (as on
Transport Request).
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Fuel Request Workflow"


def _actions(doc):
	"""The set of workflow action names currently available to the session user."""
	return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
	get_workflow_name("Fuel Request") == WORKFLOW,
	"Fuel Request Workflow not seeded on this site",
)
class TestFuelRequestWorkflow(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		# A requester (Project tier) and a separate approver (Operations tier).
		cls.requester = _user("frwf_req@example.com", "Fleet Project Manager")
		cls.manager = _user("frwf_mgr@example.com", "Fleet Manager")
		# A user who is BOTH a maker role and Fleet Manager — used to prove the SoD
		# condition is what blocks self-approval, not a role gap.
		cls.manager_maker = _user("frwf_mgrmaker@example.com", "Fleet Manager")
		frappe.get_doc("User", cls.manager_maker).add_roles("Fleet Project Manager")
		cls.project = cls._project("FR Workflow Project")
		cls.vehicle = cls._vehicle("FR-WF-1")
		# Scoped approver roles need a Project User Permission to read/transition a
		# project-scoped Fuel Request.
		for u in (cls.requester, cls.manager, cls.manager_maker):
			if not frappe.db.exists(
				"User Permission", {"user": u, "allow": "Project", "for_value": cls.project}
			):
				frappe.get_doc({
					"doctype": "User Permission",
					"user": u,
					"allow": "Project",
					"for_value": cls.project,
				}).insert(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ helpers

	@staticmethod
	def _project(name):
		p = frappe.db.get_value("Project", {"project_name": name}, "name")
		if not p:
			p = frappe.get_doc(
				{"doctype": "Project", "project_name": name}
			).insert(ignore_permissions=True).name
		return p

	@staticmethod
	def _vehicle(plate):
		v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
		if not v:
			v = frappe.get_doc(
				{"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
			).insert(ignore_permissions=True).name
		return v

	def _quota(self):
		"""A fresh Active Fuel Quota for the test vehicle/project."""
		q = frappe.get_doc({
			"doctype": "Fuel Quota",
			"vehicle": self.vehicle,
			"project": self.project,
			"period_month": "2026-05",
			"monthly_litres": 100,
			"consumed_litres": 0,
			"status": "Active",
		}).insert(ignore_permissions=True)
		self.addCleanup(lambda: self._purge_quota(q.name))
		return q

	def _new(self, request_type, requested_by=None, **overrides):
		"""A draft Fuel Request at Pending, stamped to ``requested_by`` (defaults
		to the standard requester). Inserted as Administrator so ``owner`` is
		Administrator and the SoD gate is exercised purely via requested_by."""
		data = {
			"doctype": "Fuel Request",
			"request_type": request_type,
			"vehicle": self.vehicle,
			"project": self.project,
			"requested_by": requested_by or self.requester,
			"status": "Pending",
		}
		data.update(overrides)
		doc = frappe.get_doc(data).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(lambda: self._purge(doc.name))
		return doc

	@staticmethod
	def _purge(name):
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
		frappe.db.commit()

	@staticmethod
	def _purge_quota(name):
		frappe.set_user("Administrator")
		if frappe.db.exists("Fuel Quota", name):
			frappe.delete_doc("Fuel Quota", name, ignore_permissions=True, force=True)
			frappe.db.commit()

	# ------------------------------------------------------------------ tests

	def test_workflow_is_seeded_and_active(self):
		self.assertEqual(get_workflow_name("Fuel Request"), WORKFLOW)
		self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
		)

	# --- post-submit reachability, per request_type ----------------------------

	def test_standard_post_submit_pending_approved_done(self):
		fr = self._new("Standard", requested_litres=8, amount=120)
		self.assertEqual(fr.docstatus, 0)

		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fr))
		apply_workflow(fr, "Approve")
		fr.reload()
		self.assertEqual(fr.status, "Approved")
		self.assertEqual(fr.docstatus, 1)
		# The approver is stamped (controller defence-in-depth).
		self.assertEqual(fr.approved_by, self.manager)

		# The frozen-post-submit bug: Complete must succeed on a docstatus=1 doc.
		self.assertIn("Complete", _actions(fr))
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertEqual(fr.docstatus, 1)

	def test_topup_post_submit_then_revert(self):
		fr = self._new(
			"Top-up", topup_litres=12, is_temporary=1,
			revert_due_date=frappe.utils.add_days(frappe.utils.today(), -2),
		)
		frappe.set_user(self.manager)
		apply_workflow(fr, "Approve")
		fr.reload()
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertEqual(fr.docstatus, 1)

		# Revert is offered for a Top-up and reachable post-submit.
		self.assertIn("Revert", _actions(fr))
		apply_workflow(fr, "Revert")
		fr.reload()
		self.assertEqual(fr.status, "Reverted")
		self.assertEqual(fr.docstatus, 1)

	def test_chip_post_submit_pending_approved_done(self):
		fr = self._new("Chip", action="Issue", chip_number="CHIP-WF-A")
		frappe.set_user(self.manager)
		apply_workflow(fr, "Approve")
		fr.reload()
		self.assertEqual(fr.status, "Approved")
		self.assertEqual(fr.docstatus, 1)
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertEqual(fr.docstatus, 1)

	# --- Segregation of Duties: requester cannot approve their own request ------

	def test_sod_requester_cannot_approve(self):
		# manager_maker holds BOTH Fleet Manager and Fleet Project Manager, so only
		# the SoD condition (requested_by != session.user) stands between them and
		# self-approval.
		fr = self._new("Standard", requested_by=self.manager_maker, requested_litres=5)

		frappe.set_user(self.manager_maker)
		self.assertNotIn("Approve", _actions(fr))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fr, "Approve")

		# A different Fleet Manager CAN approve the same request.
		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fr))
		apply_workflow(fr, "Approve")
		fr.reload()
		self.assertEqual(fr.status, "Approved")

	# --- type-aware transitions (the conditions) -------------------------------

	def test_revert_is_topup_only(self):
		"""A Standard request, once Done, is NOT offered Revert (Top-up only)."""
		fr = self._new("Standard", requested_litres=4, amount=60)
		frappe.set_user(self.manager)
		apply_workflow(fr, "Approve")
		fr.reload()
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertNotIn("Revert", _actions(fr))

	def test_mark_failed_is_standard_only(self):
		"""A Chip request, once Approved, is NOT offered Mark Failed (Standard
		only); a Standard request IS."""
		chip = self._new("Chip", action="Issue", chip_number="CHIP-WF-B")
		frappe.set_user(self.manager)
		apply_workflow(chip, "Approve")
		chip.reload()
		self.assertNotIn("Mark Failed", _actions(chip))

		frappe.set_user("Administrator")
		std = self._new("Standard", requested_litres=6, amount=90)
		frappe.set_user(self.manager)
		apply_workflow(std, "Approve")
		std.reload()
		self.assertIn("Mark Failed", _actions(std))
		apply_workflow(std, "Mark Failed")
		std.reload()
		self.assertEqual(std.status, "Failed")
		self.assertEqual(std.docstatus, 1)

	# --- the Standard quota side-effect fires on the post-submit Done transition -

	def test_standard_quota_applied_on_post_submit_done(self):
		q = self._quota()
		fr = self._new("Standard", requested_litres=8, amount=120, fuel_quota=q.name)

		frappe.set_user(self.manager)
		apply_workflow(fr, "Approve")
		fr.reload()
		# Not yet consumed at Approved (the side-effect is keyed on Done).
		self.assertEqual(fr.quota_applied, 0)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

		# Reaching Done post-submit applies the consumption (on_update_after_submit).
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertEqual(fr.quota_applied, 1)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 8)

		# Cancelling the Done request reverses the consumption (idempotency holds).
		frappe.set_user(self.manager)
		apply_workflow(fr, "Cancel")
		fr.reload()
		self.assertEqual(fr.status, "Cancelled")
		self.assertEqual(fr.docstatus, 2)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)
