"""Native Workflow tests for Sponsorship Transfer Case (Workflow Spine).

These lock in the conversion of Sponsorship Transfer Case from a hand-rolled
status machine to the native **Sponsorship Transfer Case Workflow**, and prove
the high-risk legal/government control: the submitting "Complete" transition
(In Progress -> Completed, docstatus 0 -> 1) is restricted to the **Fleet
Manager** (Operations tier) and gated by the workflow condition
``qiwa_status == 'Approved' and clearance_done`` — it is only offered once Qiwa
is Approved and clearance is done.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (a Government Relations Officer
    starts the case; a Fleet Manager completes it once it is gated);
  * a wrong role is blocked (a Government Relations Officer is not offered the
    submitting "Complete" action);
  * completion is blocked until gated — Complete is not offered while Qiwa is not
    Approved / clearance is not done, and the controller's _gate_completion is a
    hard server-side block (defence in depth);
  * a **post-submit transition is reachable** (Completed -> Cancelled on a
    docstatus=1 document) — the frozen-post-submit bug being fixed.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes. Sponsorship Transfer Case
is project-scoped, so the scoped Government Relations Officer is granted a
Project User Permission (mirroring test_transport_request_workflow).
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Sponsorship Transfer Case Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Sponsorship Transfer Case") == WORKFLOW,
    "Sponsorship Transfer Case Workflow not seeded on this site",
)
class TestSponsorshipTransferCaseWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.officer = _user("stc_gro@example.com", "Government Relations Officer")
        cls.manager = _user("stc_mgr@example.com", "Fleet Manager")
        cls.project = cls._project("STC Workflow Project")
        cls.employee = cls._employee("STC Workflow Employee")
        # The scoped Government Relations Officer needs a Project User Permission
        # to read/transition project-scoped Sponsorship Transfer Cases.
        if not frappe.db.exists(
            "User Permission",
            {"user": cls.officer, "allow": "Project", "for_value": cls.project},
        ):
            frappe.get_doc({
                "doctype": "User Permission",
                "user": cls.officer,
                "allow": "Project",
                "for_value": cls.project,
            }).insert(ignore_permissions=True)
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc(
                {"doctype": "Project", "project_name": name}
            ).insert(ignore_permissions=True).name
        return p

    @staticmethod
    def _employee(name):
        e = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if e:
            return e
        # Reuse any existing Employee on the site to avoid HR mandatory-field
        # coupling; the Sponsorship Transfer Case only needs a valid link.
        any_emp = frappe.db.get_value("Employee", {}, "name")
        if any_emp:
            return any_emp
        return frappe.get_doc({
            "doctype": "Employee",
            "employee_name": name,
            "first_name": name,
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "status": "Active",
        }).insert(ignore_permissions=True).name

    def _new_case(self, gated=False, **overrides):
        """A draft Sponsorship Transfer Case. When ``gated`` is True the Qiwa
        status is Approved and clearance is done so the Complete condition is
        satisfied."""
        data = {
            "doctype": "Sponsorship Transfer Case",
            "employee": self.employee,
            "project": self.project,
            "from_sponsor": "Sponsor A",
            "to_sponsor": "Sponsor B",
            "qiwa_status": "Approved" if gated else "Not Started",
            "clearance_done": 1 if gated else 0,
            "status": "Open",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _in_progress(self, **kwargs):
        stc = self._new_case(**kwargs)
        frappe.set_user(self.officer)
        apply_workflow(stc, "Start")
        frappe.set_user("Administrator")
        stc.reload()
        return stc

    # --- legal transition by the right role ------------------------------------

    def test_legal_start_then_complete(self):
        stc = self._new_case(gated=True)

        frappe.set_user(self.officer)
        self.assertIn("Start", _actions(stc))
        apply_workflow(stc, "Start")
        stc.reload()
        self.assertEqual(stc.status, "In Progress")
        self.assertEqual(stc.docstatus, 0)

        # Complete submits the document (docstatus 0 -> 1), Operations tier only.
        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(stc))
        apply_workflow(stc, "Complete")
        stc.reload()
        self.assertEqual(stc.status, "Completed")
        self.assertEqual(stc.docstatus, 1)

    # --- wrong role is blocked -------------------------------------------------

    def test_wrong_role_cannot_complete(self):
        stc = self._in_progress(gated=True)
        # The Government Relations Officer is offered no submitting Complete.
        frappe.set_user(self.officer)
        self.assertNotIn("Complete", _actions(stc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(stc, "Complete")

    # --- completion blocked until gated ----------------------------------------

    def test_complete_blocked_until_gated(self):
        # Not gated: Qiwa not Approved, clearance not done.
        stc = self._in_progress(gated=False)

        # The condition removes the Complete action for the Operations tier too.
        frappe.set_user(self.manager)
        self.assertNotIn("Complete", _actions(stc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(stc, "Complete")

        # Gate it (Qiwa Approved + clearance done) and the action appears.
        frappe.set_user("Administrator")
        stc.qiwa_status = "Approved"
        stc.clearance_done = 1
        stc.save(ignore_permissions=True)
        stc.reload()

        frappe.set_user(self.manager)
        self.assertIn("Complete", _actions(stc))
        apply_workflow(stc, "Complete")
        stc.reload()
        self.assertEqual(stc.status, "Completed")
        self.assertEqual(stc.docstatus, 1)

    def test_gate_completion_is_hard_block_on_direct_save(self):
        # Defence in depth: a direct save into Completed without the gate is
        # rejected by the controller, independent of the workflow.
        stc = self._new_case(gated=False)
        stc.status = "Completed"
        with self.assertRaises(frappe.ValidationError):
            stc.save(ignore_permissions=True)

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

    def test_post_submit_cancel_reachable(self):
        stc = self._in_progress(gated=True)
        frappe.set_user(self.manager)
        apply_workflow(stc, "Complete")
        stc.reload()
        self.assertEqual(stc.status, "Completed")
        self.assertEqual(stc.docstatus, 1)

        # The frozen-post-submit bug: a transition off a docstatus=1 document is
        # reachable (Cancel -> docstatus 2).
        self.assertIn("Cancel", _actions(stc))
        apply_workflow(stc, "Cancel")
        stc.reload()
        self.assertEqual(stc.status, "Cancelled")
        self.assertEqual(stc.docstatus, 2)
