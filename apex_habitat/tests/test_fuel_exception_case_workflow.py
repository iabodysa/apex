"""Native Workflow tests for Fuel Exception Case (Workflow Spine).

These lock in the conversion of the Fuel Exception Case from a hand-rolled status
machine (the old ``_ALLOWED_TRANSITIONS`` map + ``_enforce_status_flow``) to the
native **Fuel Exception Case Workflow**, and prove the behaviours the workflow
now owns plus the controls the controller still owns:

  * the workflow is seeded and active for Fuel Exception Case;
  * the investigation happy path: Open -> Under Investigation -> Evidence
    Required -> Resolved (submit, docstatus 0 -> 1) is reachable, and a
    **post-submit transition** Resolved -> Closed (docstatus 1 update) finalizes
    it — the frozen-post-submit bug being fixed;
  * Segregation of Duties — the (server-stamped) raiser cannot resolve their own
    case (the Resolve transition is ``allow_self_approval=0`` and carries
    ``reported_by != session.user``); a different resolver can. The controller's
    evidence-before-resolution + non-raiser-closer gate holds alongside it;
  * the Operations-tier Delegation-of-Authority gate still fires on submit;
  * the Reject exit is reachable (docstatus 0 -> 1) and Rejected -> Closed
    (docstatus 1 update) finalizes it.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Fuel Exception Case is
project-scoped, so the (unscoped) Fleet Manager resolver needs no Project User
Permission, but one is granted defensively as on Fuel Request.
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Fuel Exception Case Workflow"


def _actions(doc):
	"""The set of workflow action names currently available to the session user."""
	return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
	get_workflow_name("Fuel Exception Case") == WORKFLOW,
	"Fuel Exception Case Workflow not seeded on this site",
)
class TestFuelExceptionCaseWorkflow(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		# A raiser (Project tier) and a separate resolver (Operations tier). A user
		# who is BOTH a maker role and Fleet Manager proves the SoD condition is
		# what blocks self-resolution, not a role gap.
		cls.raiser = _user("fecw_raiser@example.com", "Fleet Project Manager")
		cls.manager = _user("fecw_mgr@example.com", "Fleet Manager")
		cls.manager_maker = _user("fecw_mgrmaker@example.com", "Fleet Manager")
		frappe.get_doc("User", cls.manager_maker).add_roles("Fleet Project Manager")
		cls.project = cls._project("FEC Workflow Project")
		cls.vehicle = cls._vehicle("FEC-WF-1")
		for u in (cls.raiser, cls.manager, cls.manager_maker):
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

	def _new(self, reported_by=None, with_evidence=True, **overrides):
		"""An Open Fuel Exception Case, raised by ``reported_by`` (defaults to the
		standard raiser). Inserted as Administrator so ``owner`` is Administrator
		and the SoD gate is exercised purely via reported_by. Evidence notes are
		supplied by default so the controller's evidence-before-resolution gate
		does not mask the workflow assertions."""
		data = {
			"doctype": "Fuel Exception Case",
			"vehicle": self.vehicle,
			"project": self.project,
			"exception_type": "Over-Consumption",
			"description": "Workflow test case.",
			"reported_by": reported_by or self.raiser,
			"status": "Open",
		}
		if with_evidence:
			data["evidence_notes"] = "GPS log attached."
		data.update(overrides)
		doc = frappe.get_doc(data).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(lambda: self._purge(doc.name))
		return doc

	def _approve_request_for(self, doc, approver=None):
		"""Mint an approved, submitted Approval Request for ``doc`` so the
		controller's Operations-tier Delegation-of-Authority gate (before_submit)
		is satisfied. The approver defaults to the Operations-tier Fleet Manager
		and differs from the raiser."""
		ar = frappe.get_doc({
			"doctype": "Approval Request",
			"request_type": "Other",
			"requested_by": doc.reported_by,
			"approver": approver or self.manager,
			"reference_doctype": "Fuel Exception Case",
			"reference_name": doc.name,
			"decision": "Approved",
		}).insert(ignore_permissions=True)
		ar.submit()
		self.addCleanup(lambda: self._purge_ar(ar.name))
		frappe.db.commit()
		return ar

	def _investigating(self, **kwargs):
		"""A case advanced to Under Investigation (still docstatus 0)."""
		fec = self._new(**kwargs)
		frappe.set_user(self.manager)
		apply_workflow(fec, "Start Investigation")
		frappe.set_user("Administrator")
		fec.reload()
		return fec

	@staticmethod
	def _purge(name):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Fuel Exception Case", name):
			return
		doc = frappe.get_doc("Fuel Exception Case", name)
		if doc.docstatus == 1:
			try:
				doc.cancel()
			except Exception:
				pass
		frappe.delete_doc("Fuel Exception Case", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	@staticmethod
	def _purge_ar(name):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Approval Request", name):
			return
		doc = frappe.get_doc("Approval Request", name)
		if doc.docstatus == 1:
			try:
				doc.cancel()
			except Exception:
				pass
		frappe.delete_doc("Approval Request", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	# ------------------------------------------------------------------ tests

	def test_workflow_is_seeded_and_active(self):
		self.assertEqual(get_workflow_name("Fuel Exception Case"), WORKFLOW)
		self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
		)

	# --- happy path incl. the post-submit transition ---------------------------

	def test_investigate_resolve_then_close(self):
		fec = self._new()
		self.assertEqual(fec.docstatus, 0)

		frappe.set_user(self.manager)
		self.assertIn("Start Investigation", _actions(fec))
		apply_workflow(fec, "Start Investigation")
		fec.reload()
		self.assertEqual(fec.status, "Under Investigation")
		self.assertEqual(fec.docstatus, 0)

		self.assertIn("Request Evidence", _actions(fec))
		apply_workflow(fec, "Request Evidence")
		fec.reload()
		self.assertEqual(fec.status, "Evidence Required")

		self.assertIn("Resume Investigation", _actions(fec))
		apply_workflow(fec, "Resume Investigation")
		fec.reload()
		self.assertEqual(fec.status, "Under Investigation")

		# Resolve submits (docstatus 0 -> 1), gated by the DoA approval + evidence.
		self._approve_request_for(fec)
		self.assertIn("Resolve", _actions(fec))
		apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.status, "Resolved")
		self.assertEqual(fec.docstatus, 1)
		# The non-raiser closer is stamped (controller defence-in-depth).
		self.assertEqual(fec.closed_by, self.manager)

		# The frozen-post-submit bug: Close must succeed on a docstatus=1 doc.
		# Closed is a docstatus-1 finalize (not a cancel), so it stays submitted.
		self.assertIn("Close", _actions(fec))
		apply_workflow(fec, "Close")
		fec.reload()
		self.assertEqual(fec.status, "Closed")
		self.assertEqual(fec.docstatus, 1)

	# --- Reject exit ------------------------------------------------------------

	def test_reject_then_close(self):
		fec = self._investigating()
		self._approve_request_for(fec)
		frappe.set_user(self.manager)
		self.assertIn("Reject", _actions(fec))
		apply_workflow(fec, "Reject")
		fec.reload()
		self.assertEqual(fec.status, "Rejected")
		self.assertEqual(fec.docstatus, 1)

		self.assertIn("Close", _actions(fec))
		apply_workflow(fec, "Close")
		fec.reload()
		self.assertEqual(fec.status, "Closed")
		self.assertEqual(fec.docstatus, 1)

	# --- Segregation of Duties: raiser cannot resolve their own case ------------

	def test_sod_raiser_cannot_resolve(self):
		# manager_maker holds BOTH Fleet Manager and Fleet Project Manager, so only
		# the SoD condition (reported_by != session.user) stands between them and
		# self-resolution.
		fec = self._investigating(reported_by=self.manager_maker)
		self._approve_request_for(fec, approver=self.manager)

		frappe.set_user(self.manager_maker)
		self.assertNotIn("Resolve", _actions(fec))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fec, "Resolve")

		# A different Fleet Manager CAN resolve the same case.
		frappe.set_user(self.manager)
		self.assertIn("Resolve", _actions(fec))
		apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.status, "Resolved")
		self.assertEqual(fec.docstatus, 1)

	# --- the Delegation-of-Authority gate still fires on submit -----------------

	def test_resolve_blocked_without_doa_approval(self):
		"""Without an approved Approval Request the Resolve transition is offered
		(role + SoD pass) but submit is blocked by the controller's DoA gate."""
		fec = self._investigating()
		frappe.set_user(self.manager)
		self.assertIn("Resolve", _actions(fec))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.docstatus, 0)
		self.assertEqual(fec.status, "Under Investigation")

	# --- evidence is required before resolution (controller gate) ---------------

	def test_resolve_blocked_without_evidence(self):
		fec = self._investigating(with_evidence=False)
		self._approve_request_for(fec)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.docstatus, 0)
