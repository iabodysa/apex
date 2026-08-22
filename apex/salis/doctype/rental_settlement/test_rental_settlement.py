# Copyright (c) 2026, afmcoltd
"""What a Rental Settlement guarantees, asserted against the DocType itself.

One live settlement per rental office per period: a second one while the
first is still live (docstatus < 2) would let the same month's accrual be
claimed twice. Marking a settlement Paid is segregation-of-duties gated: the
person who requested it may never be the one who marks it paid — enforced by
the workflow transition's own ``condition`` (``requested_by !=
session.user``), which the Approve transition on the same document also
carries, so reaching Approved at all already requires a second identity.

The SoD chain needs a real, distinct session identity with both the Fleet
Manager and Finance Manager roles the Approve and Mark Paid transitions
require, and no fixture or dependency here already provides one, so this file
creates exactly one extra user as part of the one test that needs it.
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = []

_SECOND_APPROVER = "rental-settlement-sod-test@example.invalid"


def _ensure_second_approver():
    if not frappe.db.exists("User", _SECOND_APPROVER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SECOND_APPROVER,
                "first_name": "Rental Settlement SoD Approver",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Manager"}, {"role": "Finance Manager"}],
            }
        ).insert(ignore_permissions=True)
    return _SECOND_APPROVER


class TestRentalSettlement(FrappeTestCase):
    def test_a_duplicate_live_settlement_for_the_same_office_and_period_is_refused(self):
        """A second settlement for the same office and month would double-claim the accrual."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Rental Settlement")[0])
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already covers office",
            duplicate.insert,
        )

    def test_the_requester_cannot_mark_their_own_settlement_paid(self):
        """Segregation of duties: requesting and marking paid must never be the same person."""
        approver = _ensure_second_approver()

        settlement = frappe.copy_doc(frappe.get_test_records("Rental Settlement")[0])
        settlement.period_month = "2026-09"
        settlement.insert()
        self.assertEqual(settlement.requested_by, frappe.session.user)

        reconciled = apply_workflow(settlement, "Reconcile")
        with self.set_user(approver):
            approved = apply_workflow(reconciled, "Approve")
        self.assertEqual(approved.status, "Approved")

        self.assertRaisesRegex(
            WorkflowTransitionError,
            "Not a valid Workflow Action",
            lambda: apply_workflow(approved, "Mark Paid"),
        )

        with self.set_user(approver):
            paid = apply_workflow(approved, "Mark Paid")
        self.assertEqual(paid.status, "Paid")
        self.assertEqual(paid.docstatus, 1)
