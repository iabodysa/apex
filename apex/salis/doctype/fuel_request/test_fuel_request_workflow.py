# Copyright (c) 2026, AFMCO and contributors
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

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user
from apex.tests.factories import make_project, make_vehicle, purge_doc

WORKFLOW = "Fuel Request Workflow"


def _actions(doc):
	"""The set of workflow action names currently available to the session user."""
	return {t.action for t in get_transitions(doc)}


class TestFuelRequestWorkflow(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A-077: mandatory Salis workflow (salis_workflow_seed, every install/migrate);
		# absence is a regression - FAIL, never skip.
		if get_workflow_name("Fuel Request") != WORKFLOW:
			raise AssertionError(
				f"Mandatory Salis workflow {WORKFLOW!r} not active for "
				"'Fuel Request' (salis_workflow_seed regression)"
			)
		frappe.set_user("Administrator")
		# [#mom18y]
		cls.requester = _user("frwf_req@example.com", "Fleet Project Manager")
		cls.manager = _user("frwf_mgr@example.com", "Fleet Manager")
		# [#npt94d]
		cls.manager_maker = _user("frwf_mgrmaker@example.com", "Fleet Manager")
		frappe.get_doc("User", cls.manager_maker).add_roles("Fleet Project Manager")
		cls.project = make_project("FR Workflow Project")
		cls.vehicle = make_vehicle("FR-WF-1")
		# [#pwic2j]
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

	@classmethod
	def tearDownClass(cls):
		# [#deveym]
		frappe.set_user("Administrator")
		for u in (cls.requester, cls.manager, cls.manager_maker):
			frappe.db.delete("User Permission",
				{"user": u, "allow": "Project", "for_value": cls.project})
		if frappe.db.exists("Salis Vehicle", cls.vehicle):
			frappe.delete_doc("Salis Vehicle", cls.vehicle, ignore_permissions=True, force=True)
		if frappe.db.exists("Project", cls.project):
			frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	# [#m88md8]

	def _quota(self, monthly_litres=100):
		"""A fresh Active Fuel Quota for the test vehicle/project."""
		q = frappe.get_doc({
			"doctype": "Fuel Quota",
			"vehicle": self.vehicle,
			"project": self.project,
			"period_month": "2026-05",
			"monthly_litres": monthly_litres,
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
		self.addCleanup(lambda: purge_doc("Fuel Request", doc.name))
		return doc

	@staticmethod
	def _purge_quota(name):
		frappe.set_user("Administrator")
		if frappe.db.exists("Fuel Quota", name):
			frappe.delete_doc("Fuel Quota", name, ignore_permissions=True, force=True)

	# [#stmhgc]

	def test_workflow_is_seeded_and_active(self):
		self.assertEqual(get_workflow_name("Fuel Request"), WORKFLOW)
		self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
		)

	# [#m9pgqc]

	def test_standard_post_submit_pending_approved_done(self):
		fr = self._new("Standard", requested_litres=8, amount=120)
		self.assertEqual(fr.docstatus, 0)

		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fr))
		apply_workflow(fr, "Approve")
		fr.reload()
		self.assertEqual(fr.status, "Approved")
		self.assertEqual(fr.docstatus, 1)
		# [#6vbrv7]
		self.assertEqual(fr.approved_by, self.manager)

		# [#ph0ivm]
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

		# [#gtncgf]
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

	# [#fys6d3]

	def test_sod_requester_cannot_approve(self):
		# [#61e573]
		fr = self._new("Standard", requested_by=self.manager_maker, requested_litres=5)

		frappe.set_user(self.manager_maker)
		self.assertNotIn("Approve", _actions(fr))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fr, "Approve")

		# [#psl18k]
		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fr))
		apply_workflow(fr, "Approve")
		fr.reload()
		self.assertEqual(fr.status, "Approved")

	# [#toifw5]

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

	# [#cj1ock]

	def test_standard_quota_applied_on_post_submit_done(self):
		q = self._quota()
		fr = self._new("Standard", requested_litres=8, amount=120, fuel_quota=q.name)

		frappe.set_user(self.manager)
		apply_workflow(fr, "Approve")
		fr.reload()
		# [#lbzv3j]
		self.assertEqual(fr.quota_applied, 0)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

		# [#5uqtx1]
		apply_workflow(fr, "Complete")
		fr.reload()
		self.assertEqual(fr.status, "Done")
		self.assertEqual(fr.quota_applied, 1)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 8)

		# [#r6gkdq]
		frappe.set_user(self.manager)
		apply_workflow(fr, "Cancel")
		fr.reload()
		self.assertEqual(fr.status, "Cancelled")
		self.assertEqual(fr.docstatus, 2)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

	def test_exhausted_quota_blocks_a_second_standard_draw(self):
		"""An Exhausted quota must refuse the next Standard draw instead of letting
		it approve and overrun the allocation. Top-up is the sanctioned way to add
		fuel beyond the quota, so it must stay approvable against the same quota."""
		q = self._quota(monthly_litres=10)

		first = self._new("Standard", requested_litres=10, amount=150, fuel_quota=q.name)
		frappe.set_user(self.manager)
		apply_workflow(first, "Approve")
		first.reload()
		apply_workflow(first, "Complete")
		first.reload()
		self.assertEqual(first.status, "Done")
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "status"), "Exhausted")

		# The exhausted quota must refuse the next Standard draw and stay at 10 L.
		frappe.set_user("Administrator")
		second = self._new("Standard", requested_litres=5, amount=75, fuel_quota=q.name)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(second, "Approve")
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)
		self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "quota_applied"), 0)

		# A Top-up against the very same exhausted quota still goes through.
		frappe.set_user("Administrator")
		topup = self._new("Top-up", topup_litres=5, fuel_quota=q.name)
		frappe.set_user(self.manager)
		apply_workflow(topup, "Approve")
		topup.reload()
		apply_workflow(topup, "Complete")
		topup.reload()
		self.assertEqual(topup.status, "Done")
		self.assertEqual(topup.docstatus, 1)
		# A Top-up posts no quota consumption, so the quota is untouched.
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)

	def test_oversized_first_standard_draw_is_refused(self):
		"""A FIRST draw larger than the whole allocation must be refused too.

		The exhaustion test alone cannot see this one: 15 L against a 10 L quota
		with nothing consumed satisfies ``consumed < monthly``, so the request used
		to approve, complete, and push consumed_litres to 15 — a silent 5 L overrun
		that only a msgprint on the quota ever mentioned. Top-up is the sanctioned
		way to draw beyond the allocation, so the same 15 L as a Top-up must still
		go through."""
		q = self._quota(monthly_litres=10)

		oversized = self._new("Standard", requested_litres=15, amount=225, fuel_quota=q.name)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(oversized, "Approve")

		# Refused before submit: nothing consumed, nothing submitted, no flag set.
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "status"), "Active")
		self.assertEqual(frappe.db.get_value("Fuel Request", oversized.name, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Fuel Request", oversized.name, "quota_applied"), 0)

		# The same size as a Top-up is the sanctioned route and stays open.
		frappe.set_user("Administrator")
		topup = self._new("Top-up", topup_litres=15, fuel_quota=q.name)
		frappe.set_user(self.manager)
		apply_workflow(topup, "Approve")
		topup.reload()
		apply_workflow(topup, "Complete")
		topup.reload()
		self.assertEqual(topup.status, "Done")
		self.assertEqual(topup.docstatus, 1)
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

	def test_two_in_flight_draws_cannot_jointly_overrun_the_quota(self):
		"""Each draw fits alone, both approve, and the second is caught at Complete.

		This is why the gate is re-checked inside the locked consumption step and
		not only before submit: at Approve time both 6 L requests fit the 10 L
		allocation, and only the authoritative read after the first one posts can
		see that the second would overrun. Asserted on the SIDE EFFECT
		(consumed_litres / quota_applied), never on the status field — Frappe writes
		the row before ``on_update_after_submit`` runs, so the status is not
		evidence of whether the hook refused."""
		q = self._quota(monthly_litres=10)

		first = self._new("Standard", requested_litres=6, amount=90, fuel_quota=q.name)
		second = self._new("Standard", requested_litres=6, amount=90, fuel_quota=q.name)

		frappe.set_user(self.manager)
		apply_workflow(first, "Approve")
		first.reload()
		apply_workflow(second, "Approve")
		second.reload()
		# Both fit the allocation on their own, so both reach Approved.
		self.assertEqual(first.docstatus, 1)
		self.assertEqual(second.docstatus, 1)

		apply_workflow(first, "Complete")
		first.reload()
		self.assertEqual(first.status, "Done")
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 6)

		# 6 + 6 > 10: the locked read refuses the second draw at Complete.
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(second, "Complete")
		self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 6)
		self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "quota_applied"), 0)
