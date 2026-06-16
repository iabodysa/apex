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
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests._helpers import _user

WORKFLOW = "Fuel Exception Case Workflow"


def _actions(doc):
	"""The set of workflow action names currently available to the session user."""
	return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
	get_workflow_name("Fuel Exception Case") == WORKFLOW,
	"Fuel Exception Case Workflow not seeded on this site",
)
class TestFuelExceptionCaseWorkflow(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# [#8xce09]
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
		self.addCleanup(lambda: self._purge(doc.name))
		return doc

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

	# [#stmhgc]

	def test_workflow_is_seeded_and_active(self):
		self.assertEqual(get_workflow_name("Fuel Exception Case"), WORKFLOW)
		self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
		self.assertEqual(
			frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
		)

	# [#cu9yjg]

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

		# [#abcjy2]
		self.assertIn("Resolve", _actions(fec))
		apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.status, "Resolved")
		self.assertEqual(fec.docstatus, 1)
		# [#ewwn4o]
		self.assertEqual(fec.closed_by, self.manager)

		# [#6nye7p]
		self.assertIn("Close", _actions(fec))
		apply_workflow(fec, "Close")
		fec.reload()
		self.assertEqual(fec.status, "Closed")
		self.assertEqual(fec.docstatus, 1)

	# [#udtfr4]

	def test_reject_then_close(self):
		fec = self._investigating()
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

	# [#4c4gtv]

	def test_sod_raiser_cannot_resolve(self):
		# [#57qim8]
		fec = self._investigating(reported_by=self.manager_maker)

		frappe.set_user(self.manager_maker)
		self.assertNotIn("Resolve", _actions(fec))
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fec, "Resolve")

		# [#rnl62q]
		frappe.set_user(self.manager)
		self.assertIn("Resolve", _actions(fec))
		apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.status, "Resolved")
		self.assertEqual(fec.docstatus, 1)

	# [#eqvzoy]

	def test_resolve_succeeds_via_workflow_gate(self):
		"""Approval authority now lives in the native workflow's Resolve transition
		(authorized role + SoD); the old controller-side Delegation-of-Authority
		gate (ensure_approval / Approval Request) was removed, so an authorized
		approver resolves straight through it (the separate evidence gate stays)."""
		fec = self._investigating()
		frappe.set_user(self.manager)
		self.assertIn("Resolve", _actions(fec))
		apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.docstatus, 1)

	# [#3ztwsi]

	def test_resolve_blocked_without_evidence(self):
		fec = self._investigating(with_evidence=False)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(fec, "Resolve")
		fec.reload()
		self.assertEqual(fec.docstatus, 0)
