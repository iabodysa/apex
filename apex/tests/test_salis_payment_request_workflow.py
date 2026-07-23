# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for Salis Payment Request (Workflow Spine).

These lock in the conversion of Salis Payment Request from a hand-rolled status
machine to the native **Salis Payment Request Workflow**, and prove the finance
boundary: the "Approve (Finance)" and "Mark Paid" transitions are
**Finance-Manager-only** and carry the Segregation-of-Duties condition
``requested_by != session.user`` so the (server-stamped) requester can never
approve or pay a request they raised. The same maker != checker rule is also
held at the permission layer (``permissions.payment_sod_has_permission``) — both
gates stand (defence in depth).

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (an operational maker submits to
    finance; a Finance Manager approves then pays);
  * a wrong role is blocked (an operational role is offered no finance action);
  * Approve / Mark Paid are Finance-only — a Fleet Manager is not offered them;
  * SoD — the requester (even holding the Finance Manager role) cannot approve
    or pay their own request; a different Finance Manager can;
  * a **post-submit transition is reachable** (Approved by Finance -> Paid on a
    docstatus=1 document) — the frozen-post-submit bug being fixed;
  * the no-GL boundary holds: Mark Paid posts no GL/Payment Entry.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Salis Payment Request IS
project-scoped (a scoped operational maker may only act on requests in a project
they hold a User Permission for), so the maker is granted a User Permission on
the project these fixtures use and every request is stamped with that project.
The Finance Manager approver is a cross-project finance-control role
(UNSCOPED_ROLES) and needs no project grant.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.tests._helpers import _user

WORKFLOW = "Salis Payment Request Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestSalisPaymentRequestWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A-077: mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Salis Payment Request") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Salis Payment Request' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        # [#ev7ecg]
        cls.maker = _user("pr_maker@example.com", "Fleet Project Manager")
        cls.manager = _user("pr_mgr@example.com", "Fleet Manager")
        cls.finance = _user("pr_fin@example.com", "Finance Manager")
        # [#qov9sz]
        cls.finance_maker = _user("pr_finmaker@example.com", "Finance Manager")
        frappe.get_doc("User", cls.finance_maker).add_roles("Fleet Project Manager")
        # [#djtbkz]
        cls.project = cls._project("PR Workflow Project")
        for u in (cls.maker, cls.finance_maker):
            cls._grant_project(u, cls.project)

    @classmethod
    def tearDownClass(cls):
        # [#5aa0v7]
        frappe.set_user("Administrator")
        for u in (cls.maker, cls.finance_maker):
            frappe.db.delete("User Permission",
                             {"allow": "Project", "for_value": cls.project, "user": u})
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True
            ).name
        return p

    @staticmethod
    def _grant_project(user, project):
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": project, "user": user}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Project",
                    "for_value": project,
                    "user": user,
                }
            ).insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _new_request(self, requested_by=None, **overrides):
        """A draft Salis Payment Request stamped to ``requested_by`` (defaults to
        the standard maker). Inserted as Administrator so ``owner`` is
        Administrator and the SoD gate is exercised purely via requested_by."""
        data = {
            "doctype": "Salis Payment Request",
            "expense_type": "Fuel",
            "amount": 250,
            "requested_by": requested_by or self.maker,
            "project": self.project,
            "status": "Draft",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _pending(self, **kwargs):
        pr = self._new_request(**kwargs)
        frappe.set_user(self.maker)
        apply_workflow(pr, "Submit to Finance")
        frappe.set_user("Administrator")
        pr.reload()
        return pr

    def _approved(self, **kwargs):
        pr = self._pending(**kwargs)
        frappe.set_user(self.finance)
        apply_workflow(pr, "Approve (Finance)")
        frappe.set_user("Administrator")
        pr.reload()
        return pr

    # [#6regdy]

    def test_legal_submit_then_approve_submits(self):
        pr = self._new_request()
        self.assertEqual(pr.docstatus, 0)

        frappe.set_user(self.maker)
        self.assertIn("Submit to Finance", _actions(pr))
        apply_workflow(pr, "Submit to Finance")
        pr.reload()
        self.assertEqual(pr.status, "Pending Finance")
        self.assertEqual(pr.docstatus, 0)

        # [#b002ev]
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")
        self.assertEqual(pr.docstatus, 1)
        # [#he603w]
        self.assertEqual(pr.finance_approved_by, self.finance)

    # [#rwqrmp]

    def test_wrong_role_cannot_approve_or_pay(self):
        pr = self._pending()
        # [#q1y6wf]
        frappe.set_user(self.manager)
        offered = _actions(pr)
        self.assertNotIn("Approve (Finance)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")

    # [#ong74l]

    def test_approve_and_pay_are_finance_only(self):
        pr = self._pending()

        # [#g1vfqm]
        frappe.set_user(self.manager)
        self.assertNotIn("Approve (Finance)", _actions(pr))

        # [#i6pb1n]
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

        # [#9cov55]
        frappe.set_user(self.manager)
        self.assertNotIn("Mark Paid", _actions(pr))
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)

    # [#3ehyhh]

    def test_sod_requester_cannot_approve(self):
        # [#sfheu6]
        pr = self._pending(requested_by=self.finance_maker)

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Approve (Finance)", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")

        # [#9tcigo]
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

    def test_sod_requester_cannot_mark_paid(self):
        # [#q2q4o5]
        pr = self._approved(requested_by=self.finance_maker)
        self.assertEqual(pr.status, "Approved by Finance")

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Mark Paid", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Mark Paid")

        # [#cbtqkf]
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")

    # [#4l0dab]

    def test_post_submit_mark_paid_reachable(self):
        pr = self._approved()
        self.assertEqual(pr.docstatus, 1)

        # [#j1qu0h]
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)
        # [#opmjof]
        self.assertEqual(pr.finance_approved_by, self.finance)

    # [#3sowtq]

    def test_mark_paid_posts_no_gl(self):
        pr = self._approved()
        frappe.set_user(self.finance)
        apply_workflow(pr, "Mark Paid")
        frappe.set_user("Administrator")
        pr.reload()
        self.assertEqual(pr.status, "Paid")

        # [#snwj4c]
        if frappe.db.exists("DocType", "GL Entry"):
            gl = frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Salis Payment Request", "voucher_no": pr.name},
                limit=1,
            )
            self.assertEqual(gl, [])
        self.assertFalse(pr.linked_payment_entry)
