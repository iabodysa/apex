# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Fuel Claim (Workflow Spine).

These lock in the conversion of the Fuel Claim from a hand-rolled status machine
(the old ``_ALLOWED_TRANSITIONS`` map + ``_enforce_status_flow``) to the native
**Fuel Claim Workflow**, and prove the behaviours the workflow now owns plus the
controls the controller still owns:

  * the workflow is seeded and active for Fuel Claim;
  * the reconcile-then-approve happy path: Draft -> Submitted to Movement ->
    Reconciled -> Approved (submit, docstatus 0 -> 1) is reachable, and a
    **post-submit transition** Approved -> Closed (docstatus 1 update) finalizes
    it — the frozen-post-submit bug being fixed;
  * Segregation of Duties — the (server-stamped) requester cannot approve their
    own claim (the approval transition is ``allow_self_approval=0`` and carries
    ``requested_by != session.user``); a different approver can;
  * the no-GL boundary holds: Approve / Close post no GL / Payment Entry.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Fuel Claim is project-scoped, so
the (unscoped) Fleet Manager approver needs no Project User Permission, but one
is granted defensively as on Fuel Request.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user

WORKFLOW = "Fuel Claim Workflow"


def _actions(doc):
	"""The set of workflow action names currently available to the session user."""
	return {t.action for t in get_transitions(doc)}


class TestFuelClaimWorkflow(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# A-077: mandatory Salis workflow (salis_workflow_seed, every install/migrate);
		# absence is a regression - FAIL, never skip.
		if get_workflow_name("Fuel Claim") != WORKFLOW:
			raise AssertionError(
				f"Mandatory Salis workflow {WORKFLOW!r} not active for "
				"'Fuel Claim' (salis_workflow_seed regression)"
			)
		frappe.set_user("Administrator")
		# [#bytxga]
		cls.requester = _user("fcw_req@example.com", "Fleet Project Manager")
		cls.manager = _user("fcw_mgr@example.com", "Fleet Manager")
		cls.manager_maker = _user("fcw_mgrmaker@example.com", "Fleet Manager")
		frappe.get_doc("User", cls.manager_maker).add_roles("Fleet Project Manager")
		cls.project = cls._project("FC Workflow Project")
		cls.vehicle = cls._vehicle("FC-WF-1")
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

	def _new(self, requested_by=None, **overrides):
		"""A draft Fuel Claim at Draft, stamped to ``requested_by`` (defaults to the
		standard requester). Inserted as Administrator so ``owner`` is
		Administrator and the SoD gate is exercised purely via requested_by."""
		data = {
			"doctype": "Fuel Claim",
			"project": self.project,
			"vehicle": self.vehicle,
			"period_month": "2026-05",
			"claimed_litres": 50,
			"requested_by": requested_by or self.requester,
			"status": "Draft",
		}
		data.update(overrides)
		doc = frappe.get_doc(data).insert(ignore_permissions=True)
		self.addCleanup(lambda: self._purge(doc.name))
		return doc

	def _reconciled(self, **kwargs):
		fc = self._new(**kwargs)
		frappe.set_user(self.manager)
		apply_workflow(fc, "Submit to Movement")
		fc.reload()
		apply_workflow(fc, "Reconcile")
		frappe.set_user("Administrator")
		fc.reload()
		return fc

	@staticmethod
	def _purge(name):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Fuel Claim", name):
			return
		doc = frappe.get_doc("Fuel Claim", name)
		if doc.docstatus == 1:
			try:
				doc.cancel()
			except Exception:
				pass
		frappe.delete_doc("Fuel Claim", name, ignore_permissions=True, force=True)

	# [#stmhgc]

	def test_workflow_is_seeded_and_active(self):
		self.assertEqual(get_workflow_name("Fuel Claim"), WORKFLOW)
		self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
		)

	# [#cu9yjg]

	def test_reconcile_approve_then_close(self):
		fc = self._new()
		self.assertEqual(fc.docstatus, 0)

		frappe.set_user(self.manager)
		self.assertIn("Submit to Movement", _actions(fc))
		apply_workflow(fc, "Submit to Movement")
		fc.reload()
		self.assertEqual(fc.status, "Submitted to Movement")
		self.assertEqual(fc.docstatus, 0)

		self.assertIn("Reconcile", _actions(fc))
		apply_workflow(fc, "Reconcile")
		fc.reload()
		self.assertEqual(fc.status, "Reconciled")
		self.assertEqual(fc.docstatus, 0)

		# [#5s7xwx]
		self.assertIn("Approve", _actions(fc))
		apply_workflow(fc, "Approve")
		fc.reload()
		self.assertEqual(fc.status, "Approved")
		self.assertEqual(fc.docstatus, 1)

		# [#828sio]
		self.assertIn("Close", _actions(fc))
		apply_workflow(fc, "Close")
		fc.reload()
		self.assertEqual(fc.status, "Closed")
		self.assertEqual(fc.docstatus, 1)

	# [#iv08wh]

	def test_dispute_then_resubmit(self):
		fc = self._reconciled()
		frappe.set_user(self.manager)
		self.assertIn("Dispute", _actions(fc))
		apply_workflow(fc, "Dispute")
		fc.reload()
		self.assertEqual(fc.status, "Disputed")
		self.assertEqual(fc.docstatus, 0)

		self.assertIn("Re-submit", _actions(fc))
		apply_workflow(fc, "Re-submit")
		fc.reload()
		self.assertEqual(fc.status, "Submitted to Movement")
		self.assertEqual(fc.docstatus, 0)

	# [#5sd83a]

	def test_sod_requester_cannot_approve(self):
		# [#61e573]
		fc = self._reconciled(requested_by=self.manager_maker)

		frappe.set_user(self.manager_maker)
		self.assertNotIn("Approve", _actions(fc))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fc, "Approve")

		# [#5k9urr]
		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fc))
		apply_workflow(fc, "Approve")
		fc.reload()
		self.assertEqual(fc.status, "Approved")
		self.assertEqual(fc.docstatus, 1)

	# [#df22x0]

	def test_approve_succeeds_via_workflow_gate(self):
		"""Approval authority now lives entirely in the native workflow's Approve
		transition (authorized role + SoD); the old controller-side Delegation-of-
		Authority gate (ensure_approval / Approval Request) was removed. An
		authorized approver submits straight through the transition."""
		fc = self._reconciled()
		frappe.set_user(self.manager)
		self.assertIn("Approve", _actions(fc))
		apply_workflow(fc, "Approve")
		fc.reload()
		self.assertEqual(fc.docstatus, 1)
		self.assertEqual(fc.status, "Approved")

	# [#b2z19z]

	def test_approve_and_close_post_no_gl(self):
		fc = self._reconciled()
		frappe.set_user(self.manager)
		apply_workflow(fc, "Approve")
		fc.reload()
		apply_workflow(fc, "Close")
		frappe.set_user("Administrator")
		fc.reload()
		self.assertEqual(fc.status, "Closed")

		if frappe.db.exists("DocType", "GL Entry"):
			gl = frappe.get_all(
				"GL Entry",
				filters={"voucher_type": "Fuel Claim", "voucher_no": fc.name},
				limit=1,
			)
			self.assertEqual(gl, [])
