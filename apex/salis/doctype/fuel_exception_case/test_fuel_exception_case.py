# Copyright (c) 2026, afmcoltd
"""What a Fuel Exception Case guarantees, asserted against the DocType itself.

A new case must be created at Open (later states are reached only through the
Fuel Exception Case Workflow). Resolving a case requires evidence. Resolving is
also segregation-of-duties gated: the person who raised the case may never be
the one who resolves it — enforced both by the workflow transition's own
``condition`` (``doc.reported_by != frappe.session.user``, checked by
``apply_workflow`` before the transition is even offered) and, in defence of
depth, by the controller's own ``_enforce_closure_controls``.

The SoD pair needs two real, distinct session identities, and no fixture or
dependency here already provides a second one, so this file creates exactly
one extra user — with only the "Fleet Manager" role the Resolve transition
requires — as part of the one test that needs it.
"""

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = []

_SECOND_APPROVER = "fuel-exception-case-sod-test@example.invalid"


def _ensure_second_approver():
    if not frappe.db.exists("User", _SECOND_APPROVER):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SECOND_APPROVER,
                "first_name": "Fuel Exception SoD Approver",
                "send_welcome_email": 0,
                "roles": [{"role": "Fleet Manager"}],
            }
        ).insert(ignore_permissions=True)
    return _SECOND_APPROVER


class TestFuelExceptionCase(FrappeTestCase):
    def test_a_new_case_created_directly_at_a_non_open_status_is_refused(self):
        """Later states are reached only through the workflow, never a direct insert."""
        case = frappe.copy_doc(frappe.get_test_records("Fuel Exception Case")[0])
        case.status = "Under Investigation"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must be created with status Open",
            case.insert,
        )

    def test_resolving_without_evidence_is_refused(self):
        """A case cannot close on suspicion alone; it needs recorded evidence.

        Resolved by the second approver, not the raiser: reusing the raiser
        here would hit the segregation-of-duties refusal first and never
        reach the evidence check this test targets.
        """
        approver = _ensure_second_approver()
        case = frappe.copy_doc(frappe.get_test_records("Fuel Exception Case")[0])
        case.evidence = None
        case.evidence_notes = None
        case.insert()
        investigating = apply_workflow(case, "Start Investigation")

        with self.set_user(approver):
            self.assertRaisesRegex(
                frappe.ValidationError,
                "Evidence required before resolving",
                lambda: apply_workflow(investigating, "Resolve"),
            )

    def test_the_raiser_cannot_resolve_their_own_case(self):
        """Segregation of duties: raising and resolving must never be the same person."""
        case = frappe.copy_doc(frappe.get_test_records("Fuel Exception Case")[0])
        case.evidence_notes = "Reviewed dashcam footage; consumption matches route."
        case.insert()
        self.assertEqual(case.reported_by, frappe.session.user)
        investigating = apply_workflow(case, "Start Investigation")

        self.assertRaisesRegex(
            WorkflowTransitionError,
            "Not a valid Workflow Action",
            lambda: apply_workflow(investigating, "Resolve"),
        )

    def test_a_different_user_can_resolve_the_case(self):
        """The same case a second, distinct user is fully entitled to resolve."""
        approver = _ensure_second_approver()

        case = frappe.copy_doc(frappe.get_test_records("Fuel Exception Case")[0])
        case.evidence_notes = "Reviewed dashcam footage; consumption matches route."
        case.insert()
        investigating = apply_workflow(case, "Start Investigation")

        with self.set_user(approver):
            resolved = apply_workflow(investigating, "Resolve")

        self.assertEqual(resolved.status, "Resolved")
        self.assertEqual(resolved.docstatus, 1)
        self.assertEqual(resolved.closed_by, approver)
