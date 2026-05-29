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
docstatus transition), not a mocked shortcut. Salis Payment Request is NOT
project-scoped, so no Project User Permission is required.
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Salis Payment Request Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Salis Payment Request") == WORKFLOW,
    "Salis Payment Request Workflow not seeded on this site",
)
class TestSalisPaymentRequestWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # An operational maker and the two finance approvers.
        cls.maker = _user("pr_maker@example.com", "Fleet Project Manager")
        cls.manager = _user("pr_mgr@example.com", "Fleet Manager")
        cls.finance = _user("pr_fin@example.com", "Finance Manager")
        # A user who is BOTH a maker role and Finance Manager — used to prove the
        # SoD condition is what blocks self-approval, not a role gap.
        cls.finance_maker = _user("pr_finmaker@example.com", "Finance Manager")
        frappe.get_doc("User", cls.finance_maker).add_roles("Fleet Project Manager")
        frappe.db.commit()

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

    # --- legal transition by the right role ------------------------------------

    def test_legal_submit_then_approve_submits(self):
        pr = self._new_request()
        self.assertEqual(pr.docstatus, 0)

        frappe.set_user(self.maker)
        self.assertIn("Submit to Finance", _actions(pr))
        apply_workflow(pr, "Submit to Finance")
        pr.reload()
        self.assertEqual(pr.status, "Pending Finance")
        self.assertEqual(pr.docstatus, 0)

        # Approve (Finance) submits the document (docstatus 0 -> 1).
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")
        self.assertEqual(pr.docstatus, 1)
        # The approver is stamped (defence-in-depth controller gate).
        self.assertEqual(pr.finance_approved_by, self.finance)

    # --- wrong role is blocked -------------------------------------------------

    def test_wrong_role_cannot_approve_or_pay(self):
        pr = self._pending()
        # A Fleet Manager (operational) is offered no finance approval action.
        frappe.set_user(self.manager)
        offered = _actions(pr)
        self.assertNotIn("Approve (Finance)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")

    # --- Approve / Mark Paid are Finance-exclusive -----------------------------

    def test_approve_and_pay_are_finance_only(self):
        pr = self._pending()

        # A Fleet Manager is NOT offered Approve (Finance).
        frappe.set_user(self.manager)
        self.assertNotIn("Approve (Finance)", _actions(pr))

        # A Finance Manager (different person from the requester) is offered it.
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

        # Mark Paid is likewise Finance-only.
        frappe.set_user(self.manager)
        self.assertNotIn("Mark Paid", _actions(pr))
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)

    # --- Segregation of Duties: requester cannot approve/pay their own ---------

    def test_sod_requester_cannot_approve(self):
        # finance_maker holds BOTH Finance Manager and Fleet Project Manager, so
        # only the SoD condition (requested_by != session.user) stands between
        # them and self-approval.
        pr = self._pending(requested_by=self.finance_maker)

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Approve (Finance)", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")

        # A different Finance Manager CAN approve the same request.
        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

    def test_sod_requester_cannot_mark_paid(self):
        # Approve as a neutral finance user, then the requester (who also holds
        # Finance Manager) must still be blocked from paying their own request.
        pr = self._approved(requested_by=self.finance_maker)
        self.assertEqual(pr.status, "Approved by Finance")

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Mark Paid", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Mark Paid")

        # A different Finance Manager CAN mark the same request paid.
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

    def test_post_submit_mark_paid_reachable(self):
        pr = self._approved()
        self.assertEqual(pr.docstatus, 1)

        # The frozen-post-submit bug: Mark Paid must succeed on a docstatus=1 doc.
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)

    # --- the no-GL boundary holds ----------------------------------------------

    def test_mark_paid_posts_no_gl(self):
        pr = self._approved()
        frappe.set_user(self.finance)
        apply_workflow(pr, "Mark Paid")
        frappe.set_user("Administrator")
        pr.reload()
        self.assertEqual(pr.status, "Paid")

        # No GL Entry / Payment Entry is created for the payment request.
        if frappe.db.exists("DocType", "GL Entry"):
            gl = frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Salis Payment Request", "voucher_no": pr.name},
                limit=1,
            )
            self.assertEqual(gl, [])
        self.assertFalse(pr.linked_payment_entry)
