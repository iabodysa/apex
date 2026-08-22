# Copyright (c) 2026, afmcoltd
"""What a Fuel Claim guarantees, asserted against the DocType itself.

A new claim must be created at Draft (later states are reached only through
the Fuel Claim Workflow). Claimed litres must be positive. ``consumed_litres``
and ``variance_litres`` are always derived from the Fuel Consumption Ledger for
the claim's own vehicle and period, never entered by hand. Approving a claim
is segregation-of-duties gated: the person who requested it may never be the
one who approves it — enforced by the workflow transition's own ``condition``
(``doc.requested_by != frappe.session.user``, checked by ``apply_workflow``
before the transition is even offered).

The SoD pair needs two real, distinct session identities, and no fixture or
dependency here already provides a second one, so this file creates exactly
one extra user — with only the "Fleet Manager" role the Approve transition
requires — as part of the one test that needs it.
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Project", "Fuel Consumption Ledger"]

_SECOND_APPROVER = "fuel-claim-sod-test@example.invalid"


def _ensure_second_approver():
    if not frappe.db.exists("User", _SECOND_APPROVER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SECOND_APPROVER,
                "first_name": "Fuel Claim SoD Approver",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Manager"}],
            }
        ).insert(ignore_permissions=True)
    return _SECOND_APPROVER


class TestFuelClaim(FrappeTestCase):
    def test_a_new_claim_created_directly_at_a_non_draft_status_is_refused(self):
        """Later states are reached only through the workflow, never a direct insert."""
        claim = frappe.copy_doc(frappe.get_test_records("Fuel Claim")[0])
        claim.status = "Submitted to Movement"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must be created with status Draft",
            claim.insert,
        )

    def test_claimed_litres_must_be_greater_than_zero(self):
        """A claim for zero or negative litres claims nothing."""
        claim = frappe.copy_doc(frappe.get_test_records("Fuel Claim")[0])
        claim.claimed_litres = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Claimed Litres must be greater than zero",
            claim.insert,
        )

    def test_consumed_and_variance_litres_are_derived_from_the_fuel_consumption_ledger(self):
        """Movement reconciles a claim against the ledger, not against the claimant's own figure."""
        claim = frappe.copy_doc(frappe.get_test_records("Fuel Claim")[0])
        claim.insert()
        self.assertEqual(claim.consumed_litres, 120.5)
        self.assertEqual(claim.variance_litres, claim.claimed_litres - 120.5)

    def test_the_requester_cannot_approve_their_own_claim(self):
        """Segregation of duties: requesting and approving must never be the same person."""
        claim = frappe.copy_doc(frappe.get_test_records("Fuel Claim")[0])
        claim.insert()
        self.assertEqual(claim.requested_by, frappe.session.user)

        submitted = apply_workflow(claim, "Submit to Movement")
        reconciled = apply_workflow(submitted, "Reconcile")

        self.assertRaisesRegex(
            WorkflowTransitionError,
            "Not a valid Workflow Action",
            lambda: apply_workflow(reconciled, "Approve"),
        )

    def test_a_different_user_can_approve_the_claim(self):
        """The same claim a second, distinct user is fully entitled to approve."""
        approver = _ensure_second_approver()

        claim = frappe.copy_doc(frappe.get_test_records("Fuel Claim")[0])
        claim.insert()
        submitted = apply_workflow(claim, "Submit to Movement")
        reconciled = apply_workflow(submitted, "Reconcile")

        with self.set_user(approver):
            approved = apply_workflow(reconciled, "Approve")

        self.assertEqual(approved.status, "Approved")
        self.assertEqual(approved.docstatus, 1)
        self.assertEqual(approved.approved_by, approver)
