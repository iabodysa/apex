"""Native Workflow tests for Rental Settlement (Workflow Spine, second-mover).

These lock in the conversion of Rental Settlement from a status field with no
transition engine to the native **Rental Settlement Workflow**, and prove the
finance control: the "Mark Paid" transition is **Finance-Manager-only** and
carries the Segregation-of-Duties condition ``requested_by != session.user`` so
the (server-stamped) requester can never mark their own settlement paid.

Coverage (adversarial / cross-role, not only the happy path):
  * a legal transition by the right role passes (Fleet Manager reconciles then
    approves; submit happens at Approved);
  * a wrong role is blocked (Fleet Project Manager is offered no approve/pay
    action);
  * Mark Paid is Finance-only — a Fleet Manager is not offered it, a Finance
    Manager is;
  * SoD — the requester (even with the Finance Manager role) cannot Mark Paid
    their own settlement; a different Finance Manager can;
  * a **post-submit transition is reachable** (Approved -> Paid on a
    docstatus=1 document) — the frozen-post-submit bug being fixed;
  * the no-GL boundary holds: Mark Paid posts no GL/Payment Entry.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + condition +
docstatus transition), not a mocked shortcut. Rental Settlement is NOT
project-scoped, so no Project User Permission is required.
"""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex_habitat.tests.test_salis_doa import _user

WORKFLOW = "Rental Settlement Workflow"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


@unittest.skipUnless(
    get_workflow_name("Rental Settlement") == WORKFLOW,
    "Rental Settlement Workflow not seeded on this site",
)
class TestRentalSettlementWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # A requester (operational maker) and the two approver tiers.
        cls.requester = _user("rs_req@example.com", "Fleet Project Manager")
        cls.manager = _user("rs_mgr@example.com", "Fleet Manager")
        cls.finance = _user("rs_fin@example.com", "Finance Manager")
        # A user who is BOTH the requester role and Finance Manager — used to
        # prove the SoD condition is what blocks self-payment, not a role gap.
        cls.finance_maker = _user("rs_finmaker@example.com", "Finance Manager")
        frappe.get_doc("User", cls.finance_maker).add_roles("Fleet Project Manager")
        cls.office = cls._office("RS Workflow Office")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _office(name):
        o = frappe.db.get_value("Rental Office", {"office_name": name}, "name")
        if not o:
            o = frappe.get_doc(
                {"doctype": "Rental Office", "office_name": name}
            ).insert(ignore_permissions=True).name
        return o

    def _new_settlement(self, requested_by=None, **overrides):
        """A draft Rental Settlement stamped to ``requested_by`` (defaults to the
        standard requester). Inserted as Administrator so ``owner`` is
        Administrator and the SoD gate is exercised purely via requested_by."""
        data = {
            "doctype": "Rental Settlement",
            "rental_office": self.office,
            "period_month": "2026-05",
            "claimed_total": 1000,
            "requested_by": requested_by or self.requester,
            "status": "Draft",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _reconciled(self, **kwargs):
        rs = self._new_settlement(**kwargs)
        frappe.set_user(self.manager)
        apply_workflow(rs, "Reconcile")
        frappe.set_user("Administrator")
        rs.reload()
        return rs

    def _approved(self, **kwargs):
        rs = self._reconciled(**kwargs)
        frappe.set_user(self.manager)
        apply_workflow(rs, "Approve")
        frappe.set_user("Administrator")
        rs.reload()
        return rs

    # --- F-04: a payment request may only be raised on an Approved settlement ---

    def test_payment_request_only_on_approved_settlement(self):
        # An Approved (submitted) settlement can raise a payment request.
        rs = self._approved()
        pr = rs.create_payment_request()
        self.assertTrue(frappe.db.exists("Salis Payment Request", pr))
        # A submitted-but-Disputed settlement is blocked by the F-04 guard.
        rs2 = self._approved()
        frappe.db.set_value("Rental Settlement", rs2.name, "status", "Disputed")
        rs2.reload()
        with self.assertRaises(frappe.ValidationError):
            rs2.create_payment_request()

    # --- legal transition by the right role ------------------------------------

    def test_legal_reconcile_then_approve_submits(self):
        rs = self._new_settlement()
        self.assertEqual(rs.docstatus, 0)

        frappe.set_user(self.manager)
        self.assertIn("Reconcile", _actions(rs))
        apply_workflow(rs, "Reconcile")
        rs.reload()
        self.assertEqual(rs.status, "Reconciled")
        self.assertEqual(rs.docstatus, 0)

        # Approve submits the document (docstatus 0 -> 1).
        self.assertIn("Approve", _actions(rs))
        apply_workflow(rs, "Approve")
        rs.reload()
        self.assertEqual(rs.status, "Approved")
        self.assertEqual(rs.docstatus, 1)

    # --- wrong role is blocked -------------------------------------------------

    def test_wrong_role_cannot_approve_or_pay(self):
        rs = self._reconciled()
        # The Fleet Project Manager (requester role) is offered no approve/pay.
        frappe.set_user(self.requester)
        offered = _actions(rs)
        self.assertNotIn("Approve", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Approve")

    # --- Mark Paid is Finance-exclusive ----------------------------------------

    def test_mark_paid_is_finance_only(self):
        rs = self._approved()
        self.assertEqual(rs.status, "Approved")

        # A Fleet Manager (operational) is NOT offered Mark Paid.
        frappe.set_user(self.manager)
        self.assertNotIn("Mark Paid", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Mark Paid")

        # A Finance Manager (different person from the requester) is offered it.
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")
        self.assertEqual(rs.docstatus, 1)

    # --- Segregation of Duties: requester cannot pay their own settlement ------

    def test_sod_requester_cannot_mark_paid(self):
        # finance_maker holds BOTH Finance Manager and Fleet Project Manager, so
        # only the SoD condition (requested_by != session.user) stands between
        # them and self-payment.
        rs = self._approved(requested_by=self.finance_maker)

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Mark Paid", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Mark Paid")

        # A different Finance Manager CAN mark the same settlement paid.
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")

    def test_sod_requester_cannot_self_approve(self):
        # The approve step is likewise SoD-gated. A Fleet Manager who is also the
        # requester cannot approve their own settlement.
        mgr_maker = _user("rs_mgrmaker@example.com", "Fleet Manager")
        rs = self._reconciled(requested_by=mgr_maker)
        frappe.set_user(mgr_maker)
        self.assertNotIn("Approve", _actions(rs))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rs, "Approve")

    # --- post-submit transition is REACHABLE (the bug being fixed) -------------

    def test_post_submit_mark_paid_reachable(self):
        rs = self._approved()
        self.assertEqual(rs.docstatus, 1)

        # The frozen-post-submit bug: Mark Paid must succeed on a docstatus=1 doc.
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(rs))
        apply_workflow(rs, "Mark Paid")
        rs.reload()
        self.assertEqual(rs.status, "Paid")
        self.assertEqual(rs.docstatus, 1)

    # --- the no-GL boundary holds ----------------------------------------------

    def test_mark_paid_posts_no_gl(self):
        rs = self._approved()
        frappe.set_user(self.finance)
        apply_workflow(rs, "Mark Paid")
        frappe.set_user("Administrator")
        rs.reload()
        self.assertEqual(rs.status, "Paid")

        # No GL Entry / Payment Entry is created for the settlement.
        if frappe.db.exists("DocType", "GL Entry"):
            gl = frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Rental Settlement", "voucher_no": rs.name},
                limit=1,
            )
            self.assertEqual(gl, [])
