# Copyright (c) 2026, afmcoltd
"""What a Fuel Request guarantees, asserted against the DocType itself.

A new request must be created at Pending (later states are reached only
through the Fuel Request Workflow). A Standard request needs positive
requested litres; a Chip cancellation needs inactivity evidence and owner
acknowledgement before it can submit. Approving a request is
segregation-of-duties gated: the person who requested it may never be the one
who approves it — enforced by the workflow transition's own ``condition``
(``doc.requested_by != frappe.session.user``, checked by ``apply_workflow``
before the transition is even offered). A Standard request's quota
consumption is applied exactly once, when the request reaches Done, and
reversed on cancel.

The SoD pair needs two real, distinct session identities, and no fixture or
dependency here already provides a second one, so this file creates exactly
one extra user — with only the "Fleet Manager" role the Approve transition
requires — as part of the tests that need it.
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Fuel Quota"]

_SECOND_APPROVER = "fuel-request-sod-test@example.invalid"


def _ensure_second_approver():
    if not frappe.db.exists("User", _SECOND_APPROVER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SECOND_APPROVER,
                "first_name": "Fuel Request SoD Approver",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Manager"}],
            }
        ).insert(ignore_permissions=True)
    return _SECOND_APPROVER


class TestFuelRequest(FrappeTestCase):
    def test_a_new_request_created_directly_at_a_non_pending_status_is_refused(self):
        """Later states are reached only through the workflow, never a direct insert."""
        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[0])
        request.status = "Approved"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must be created with status Pending",
            request.insert,
        )

    def test_a_standard_request_with_zero_or_negative_litres_is_refused(self):
        """A Standard draw of zero or less litres requests nothing."""
        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[0])
        request.requested_litres = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Requested Litres must be greater than zero",
            request.insert,
        )

    def test_a_chip_cancellation_without_evidence_and_acknowledgement_is_refused(self):
        """A chip cannot be cancelled on a bare say-so; the server requires the two proofs."""
        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[1])
        request.action = "Cancel"
        request.chip_number = "CHIP-0001"
        request.inactivity_evidence = None
        request.owner_acknowledged = 0
        request.insert()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Inactivity evidence is required",
            request.submit,
        )

    def test_the_requester_cannot_approve_their_own_request(self):
        """Segregation of duties: requesting and approving must never be the same person."""
        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[0])
        request.insert()
        self.assertEqual(request.requested_by, frappe.session.user)

        self.assertRaisesRegex(
            WorkflowTransitionError,
            "Not a valid Workflow Action",
            lambda: apply_workflow(request, "Approve"),
        )

    def test_a_different_user_can_approve_the_request(self):
        """The same request a second, distinct user is fully entitled to approve."""
        approver = _ensure_second_approver()

        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[0])
        request.insert()

        with self.set_user(approver):
            approved = apply_workflow(request, "Approve")

        self.assertEqual(approved.status, "Approved")
        self.assertEqual(approved.docstatus, 1)
        self.assertEqual(approved.approved_by, approver)

    def test_reaching_done_applies_quota_consumption_once_and_cancel_reverses_it(self):
        """The whole point of quota_applied is that one request moves the quota exactly once, either way."""
        approver = _ensure_second_approver()
        quota_name = frappe.db.get_value(
            "Fuel Quota", {"vehicle": "VEH-000001", "period_month": "2026-01"}
        )
        monthly = frappe.db.get_value("Fuel Quota", quota_name, "monthly_litres")

        request = frappe.copy_doc(frappe.get_test_records("Fuel Request")[0])
        request.requested_by = approver  # so Administrator may legitimately approve it below
        request.fuel_quota = quota_name
        request.requested_litres = 50
        request.insert()

        approved = apply_workflow(request, "Approve")
        self.assertEqual(
            frappe.db.get_value("Fuel Quota", quota_name, "consumed_litres"),
            0,
            "approval alone must not yet post consumption",
        )

        done = apply_workflow(approved, "Complete")
        self.assertEqual(done.status, "Done")
        self.assertEqual(frappe.db.get_value("Fuel Quota", quota_name, "consumed_litres"), 50)

        apply_workflow(done, "Cancel")
        self.assertEqual(frappe.db.get_value("Fuel Quota", quota_name, "consumed_litres"), 0)
        self.assertEqual(
            frappe.db.get_value("Fuel Quota", quota_name, "monthly_litres"),
            monthly,
            "cancelling a Standard draw must not touch the allocation itself",
        )
