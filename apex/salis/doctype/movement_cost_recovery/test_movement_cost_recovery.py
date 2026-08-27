# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float
from apex.tests.factories import make_project, make_vehicle


def _project():
    return make_project("_T-MCR Project")


def _vehicle():
    return make_vehicle("_T-MCR-0001", project=_project())


def _recovery(**overrides):
    fields = {
        "doctype": "Movement Cost Recovery",
        "recovery_type": "Vehicle Damage",
        "vehicle": _vehicle(),
        "amount": 100,
        "basis_evidence": "/files/_t_mcr_evidence.pdf",
        "request_date": frappe.utils.today(),
        "status": "Open",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _acknowledged(**overrides):
    doc = _recovery(**overrides).insert(ignore_permissions=True)
    doc.acknowledgement_received = 1
    doc.save(ignore_permissions=True)
    return doc


def _user_with_role(first_name, role):
    email = "_t_mcr_" + frappe.generate_hash(length=6) + "@example.com"
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "send_welcome_email": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    doc.add_roles(role)
    return email


def _regional_supervisor():
    email = _user_with_role("_T-MCR Regional", "Fleet Supervisor")
    frappe.get_doc(
        {
            "doctype": "User Permission",
            "user": email,
            "allow": "Project",
            "for_value": _project(),
        }
    ).insert(ignore_permissions=True)
    return email


def _approved(**overrides):
    doc = _acknowledged(**overrides)
    approver = _user_with_role("_T-MCR Fleet Manager", "Fleet Manager")
    frappe.set_user(approver)
    try:
        apply_workflow(doc, "Approve")
    finally:
        frappe.set_user("Administrator")
    return doc, approver


def _threshold():
    return get_salis_float("cost_recovery_ops_threshold", 1000.0)


class TestMovementCostRecoveryAmount(FrappeTestCase):
    def test_a_zero_amount_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _recovery(amount=0).insert(ignore_permissions=True)

    def test_a_negative_amount_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _recovery(amount=-5).insert(ignore_permissions=True)


class TestMovementCostRecoveryOperationsThreshold(FrappeTestCase):
    def test_an_amount_below_the_threshold_needs_no_operations_tier(self):
        doc = _recovery(amount=_threshold() - 1).insert(ignore_permissions=True)
        self.assertEqual(doc.needs_operations, 0)

    def test_an_amount_at_the_threshold_needs_the_operations_tier(self):
        doc = _recovery(amount=_threshold()).insert(ignore_permissions=True)
        self.assertEqual(doc.needs_operations, 1)

    def test_the_flag_follows_the_amount_rather_than_what_was_typed(self):
        doc = _recovery(amount=_threshold() - 1, needs_operations=1).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.needs_operations, 0)


class TestMovementCostRecoveryAcknowledgement(FrappeTestCase):
    def test_approving_without_an_acknowledgement_is_refused(self):
        doc = _recovery().insert(ignore_permissions=True)
        approver = _user_with_role("_T-MCR Fleet Manager", "Fleet Manager")
        frappe.set_user(approver)
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaisesRegex(frappe.ValidationError, "Acknowledgement Received"):
            apply_workflow(doc, "Approve")

    def test_an_acknowledged_recovery_below_the_threshold_is_approved(self):
        doc, _approver = _approved(amount=_threshold() - 1)
        self.assertEqual(doc.status, "Approved")


class TestMovementCostRecoverySelfApproval(FrappeTestCase):
    def test_the_raiser_cannot_approve_their_own_recovery(self):
        doc = _acknowledged(amount=_threshold() - 1)
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Approve")


class TestMovementCostRecoveryDelegationGate(FrappeTestCase):
    def test_a_regional_authority_may_authorize_below_the_operations_threshold(self):
        doc = _acknowledged(amount=_threshold() - 1)
        frappe.set_user(_regional_supervisor())
        self.addCleanup(frappe.set_user, "Administrator")
        apply_workflow(doc, "Authorize (Regional)")
        self.assertEqual(doc.status, "Approved")

    def test_a_regional_authority_cannot_authorize_above_the_operations_threshold(self):
        doc = _acknowledged(amount=_threshold())
        frappe.set_user(_regional_supervisor())
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Authorize (Regional)")

    def test_approving_above_the_threshold_without_operations_authority_is_refused(self):
        doc = _acknowledged(amount=_threshold())
        frappe.set_user(_regional_supervisor())
        self.addCleanup(frappe.set_user, "Administrator")
        doc.status = "Approved"
        with self.assertRaisesRegex(frappe.ValidationError, "Operations-tier authority"):
            doc.save()

    def test_the_operations_tier_may_approve_above_the_threshold(self):
        doc, _approver = _approved(amount=_threshold())
        self.assertEqual(doc.status, "Approved")


class TestMovementCostRecoveryFinancialDefaults(FrappeTestCase):
    def test_a_recovery_with_no_company_is_filled_from_the_salis_default(self):
        doc = _recovery().insert(ignore_permissions=True)
        self.assertTrue(doc.company)
