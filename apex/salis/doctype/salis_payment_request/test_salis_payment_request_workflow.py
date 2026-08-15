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

from apex.apex_core.payment_router import route_payment
from apex.tests._helpers import _user, submit_via_workflow
from apex.tests.factories import make_project

WORKFLOW = "Salis Payment Request Workflow"
ROUTING_SETTINGS = "Payment Routing Settings"


def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}


class TestSalisPaymentRequestWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Salis Payment Request") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Salis Payment Request' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.maker = _user("pr_maker@example.com", "Fleet Project Manager")
        cls.manager = _user("pr_mgr@example.com", "Fleet Manager")
        cls.finance = _user("pr_fin@example.com", "Finance Manager")
        cls.finance_maker = _user("pr_finmaker@example.com", "Finance Manager")
        frappe.get_doc("User", cls.finance_maker).add_roles("Fleet Project Manager")
        cls.project = make_project("PR Workflow Project")
        for u in (cls.maker, cls.finance_maker):
            cls._grant_project(u, cls.project)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for u in (cls.maker, cls.finance_maker):
            frappe.db.delete("User Permission",
                             {"allow": "Project", "for_value": cls.project, "user": u})
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

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


    def test_legal_submit_then_approve_submits(self):
        pr = self._new_request()
        self.assertEqual(pr.docstatus, 0)

        frappe.set_user(self.maker)
        self.assertIn("Submit to Finance", _actions(pr))
        apply_workflow(pr, "Submit to Finance")
        pr.reload()
        self.assertEqual(pr.status, "Pending Finance")
        self.assertEqual(pr.docstatus, 0)

        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")
        self.assertEqual(pr.docstatus, 1)
        self.assertEqual(pr.finance_approved_by, self.finance)


    def test_wrong_role_cannot_approve_or_pay(self):
        pr = self._pending()
        frappe.set_user(self.manager)
        offered = _actions(pr)
        self.assertNotIn("Approve (Finance)", offered)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")


    def test_approve_and_pay_are_finance_only(self):
        pr = self._pending()

        frappe.set_user(self.manager)
        self.assertNotIn("Approve (Finance)", _actions(pr))

        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

        frappe.set_user(self.manager)
        self.assertNotIn("Mark Paid", _actions(pr))
        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)


    def test_sod_requester_cannot_approve(self):
        pr = self._pending(requested_by=self.finance_maker)

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Approve (Finance)", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Approve (Finance)")

        frappe.set_user(self.finance)
        self.assertIn("Approve (Finance)", _actions(pr))
        apply_workflow(pr, "Approve (Finance)")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")

    def test_sod_requester_cannot_mark_paid(self):
        pr = self._approved(requested_by=self.finance_maker)
        self.assertEqual(pr.status, "Approved by Finance")

        frappe.set_user(self.finance_maker)
        self.assertNotIn("Mark Paid", _actions(pr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(pr, "Mark Paid")

        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")


    def test_post_submit_mark_paid_reachable(self):
        pr = self._approved()
        self.assertEqual(pr.docstatus, 1)

        frappe.set_user(self.finance)
        self.assertIn("Mark Paid", _actions(pr))
        apply_workflow(pr, "Mark Paid")
        pr.reload()
        self.assertEqual(pr.status, "Paid")
        self.assertEqual(pr.docstatus, 1)
        self.assertEqual(pr.finance_approved_by, self.finance)


    def test_mark_paid_posts_no_gl(self):
        pr = self._approved()
        frappe.set_user(self.finance)
        apply_workflow(pr, "Mark Paid")
        frappe.set_user("Administrator")
        pr.reload()
        self.assertEqual(pr.status, "Paid")

        if frappe.db.exists("DocType", "GL Entry"):
            gl = frappe.get_all(
                "GL Entry",
                filters={"voucher_type": "Salis Payment Request", "voucher_no": pr.name},
                limit=1,
            )
            self.assertEqual(gl, [])
        self.assertFalse(pr.linked_payment_entry)


    def test_rejected_request_can_be_revised_to_draft(self):
        # An earlier finding: a Finance rejection is not a dead end - the maker
        # revises the request back to Draft to correct and resubmit.
        pr = self._pending()
        frappe.set_user(self.finance)
        self.assertIn("Reject", _actions(pr))
        apply_workflow(pr, "Reject")
        pr.reload()
        self.assertEqual(pr.status, "Rejected")
        self.assertEqual(pr.docstatus, 0)

        frappe.set_user(self.maker)
        self.assertIn("Revise", _actions(pr))
        apply_workflow(pr, "Revise")
        pr.reload()
        self.assertEqual(pr.status, "Draft")
        self.assertEqual(pr.docstatus, 0)


class TestAmendedRequestRoutesANewPayment(FrappeTestCase):
    """An amendment is a NEW payable and must route its OWN payment.

    ``payment_router.route_payment`` short-circuits on ``linked_payment_entry``
    and returns it, so whatever the amend copy carries over IS the answer. The
    desk's amend keeps every field — ``no_copy`` is honoured only on Duplicate
    (``create_new.js``: ``is_no_copy = !from_amend && ...``) — so the cancelled
    original's link had to be cleared on the amended insert, or Finance re-reads
    a payment raised against a cancelled request.

    Targets ``Note``: a dependency-free core DocType, the same stand-in the
    router's own tests use, so the assertion is about re-routing and not about
    an accounting doctype's validations.
    """

    def setUp(self):
        frappe.set_user("Administrator")
        settings = frappe.get_single(ROUTING_SETTINGS)
        # A Single does NOT roll back with the test transaction — restore it by hand,
        # registered BEFORE the mutation so a mid-test failure still restores.
        self.addCleanup(
            self._restore,
            settings.target_payment_doctype,
            [
                {
                    "target_fieldname": r.target_fieldname,
                    "source_fieldname": r.source_fieldname,
                    "is_static": r.is_static,
                    "static_value": r.static_value,
                }
                for r in (settings.field_map or [])
            ],
        )
        settings.target_payment_doctype = "Note"
        # Draft target only: auto-submit is a separate concern and would drag in the GL gate.
        settings.auto_submit_target = 0
        settings.set("field_map", [{"target_fieldname": "title", "source_fieldname": "name"}])
        settings.save(ignore_permissions=True)

    @staticmethod
    def _restore(target, rows):
        frappe.set_user("Administrator")
        settings = frappe.get_single(ROUTING_SETTINGS)
        settings.target_payment_doctype = target
        settings.set("field_map", rows)
        settings.save(ignore_permissions=True)

    def _routable(self):
        """A submitted request carrying the finance stamp the router gates on.

        The stamp is written after submit because ``_guard_finance_stamp`` reverts any
        caller-supplied value; the approval gate itself is proven by the workflow tests
        above, so it is a fixture here rather than the subject.
        """
        doc = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Rental",
                "amount": 500,
                "remarks": "Amend re-route",
                "status": "Draft",
            }
        ).insert(ignore_permissions=True)
        submit_via_workflow(doc)
        doc.db_set("finance_approved_by", "Administrator", update_modified=False)
        doc.reload()
        return doc

    def test_amended_request_routes_a_new_payment(self):
        original = self._routable()
        first = route_payment(original.name)
        original.reload()
        self.assertEqual(original.linked_payment_entry, first)

        original.cancel()
        # The desk amend copies every field (no_copy included) and clears only
        # name/amended_from/amendment_date, which is what frappe.copy_doc does by
        # default. docstatus survives copy_doc under in_test, so reset it explicitly.
        amended = frappe.copy_doc(original)
        amended.amended_from = original.name
        amended.docstatus = 0
        # An amendment re-enters the flow as a draft. Carrying the cancelled doc's
        # "Approved by Finance" status instead would trip the SoD gate on insert —
        # a different behaviour, already covered above, and not the subject here.
        amended.status = "Draft"
        amended.insert(ignore_permissions=True)
        self.assertFalse(
            amended.linked_payment_entry,
            "the amendment inherited the cancelled original's payment link",
        )

        submit_via_workflow(amended)
        amended.db_set("finance_approved_by", "Administrator", update_modified=False)
        amended.reload()

        notes_before = frappe.db.count("Note")
        second = route_payment(amended.name)

        self.assertNotEqual(second, first, "the amendment re-returned the original's payment")
        self.assertEqual(frappe.db.count("Note"), notes_before + 1)
        amended.reload()
        self.assertEqual(amended.linked_payment_entry, second)
