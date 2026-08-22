# Copyright (c) 2026, afmcoltd
"""What a Salis Payment Request guarantees, asserted against the DocType itself.

The amount must be positive. Approving a request is segregation-of-duties
gated: the person who requested it may never be the one who approves it —
enforced by the workflow transition's own ``condition`` (``requested_by !=
session.user``, checked by ``apply_workflow`` before the transition is even
offered) and, in defence of depth, by the controller's own
``_enforce_finance_gate``.

The SoD pair needs a real, distinct session identity holding the Finance
Manager role the Approve (Finance) transition requires, and no fixture or
dependency here already provides one, so this file creates exactly one extra
user as part of the one test that needs it.
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]

_FINANCE_APPROVER = "salis-payment-request-sod-test@example.invalid"


def _ensure_finance_approver():
    if not frappe.db.exists("User", _FINANCE_APPROVER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _FINANCE_APPROVER,
                "first_name": "Payment Request SoD Approver",
                "send_welcome_email": 0,
                "roles": [{"role": "Finance Manager"}],
            }
        ).insert(ignore_permissions=True)
    return _FINANCE_APPROVER


class TestSalisPaymentRequest(FrappeTestCase):
    def test_a_zero_or_negative_amount_is_refused(self):
        """A payment request for nothing (or less) requests nothing."""
        request = frappe.copy_doc(frappe.get_test_records("Salis Payment Request")[0])
        request.amount = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Amount must be greater than zero",
            request.insert,
        )

    def test_the_requester_cannot_approve_their_own_payment_request(self):
        """Segregation of duties: requesting and approving must never be the same person."""
        approver = _ensure_finance_approver()

        request = frappe.copy_doc(frappe.get_test_records("Salis Payment Request")[0])
        request.insert()
        self.assertEqual(request.requested_by, frappe.session.user)
        pending = apply_workflow(request, "Submit to Finance")

        self.assertRaisesRegex(
            WorkflowTransitionError,
            "Not a valid Workflow Action",
            lambda: apply_workflow(pending, "Approve (Finance)"),
        )

        with self.set_user(approver):
            approved = apply_workflow(pending, "Approve (Finance)")

        self.assertEqual(approved.status, "Approved by Finance")
        self.assertEqual(approved.docstatus, 1)
        self.assertEqual(approved.finance_approved_by, approver)
