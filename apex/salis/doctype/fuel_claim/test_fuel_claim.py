# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.company import company_for_vehicle
from apex.tests.factories import make_project

_PERIOD = "2026-03"


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-FCM " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _user_with_role(first_name, role):
    email = "_t_fcm_" + frappe.generate_hash(length=6) + "@example.com"
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


def _claim(**overrides):
    fields = {
        "doctype": "Fuel Claim",
        "project": make_project("_T-FCM Project"),
        "vehicle": _vehicle(),
        "period_month": _PERIOD,
        "claimed_litres": 100,
        "claimed_amount": 250,
        "status": "Draft",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _ledger(vehicle, litres):
    frappe.get_doc(
        {
            "doctype": "Fuel Consumption Ledger",
            "vehicle": vehicle,
            "company": company_for_vehicle(vehicle),
            "period_month": _PERIOD,
            "litres": litres,
            "amount": litres * 2,
            "source_type": "Fuel Daily Log",
            "source_doctype": "Fuel Daily Log",
            "logged_at": frappe.utils.now_datetime(),
        }
    ).insert(ignore_permissions=True)


def _reconciled(**overrides):
    doc = _claim(**overrides).insert(ignore_permissions=True)
    apply_workflow(doc, "Submit to Movement")
    apply_workflow(doc, "Reconcile")
    return doc


class TestFuelClaimClaimedLitres(FrappeTestCase):
    def test_a_zero_claim_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _claim(claimed_litres=0).insert(ignore_permissions=True)

    def test_a_negative_claim_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _claim(claimed_litres=-1).insert(ignore_permissions=True)


class TestFuelClaimOpensDraft(FrappeTestCase):
    def test_a_claim_created_at_a_later_status_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "must be created with status Draft"):
            _claim(status="Reconciled").insert(ignore_permissions=True)

    def test_a_claim_created_draft_is_accepted(self):
        doc = _claim().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Draft")


class TestFuelClaimRequester(FrappeTestCase):
    def test_a_claim_with_no_requester_names_the_session_user(self):
        doc = _claim().insert(ignore_permissions=True)
        self.assertEqual(doc.requested_by, frappe.session.user)


class TestFuelClaimUnitPrice(FrappeTestCase):
    def test_the_unit_price_is_the_amount_over_the_litres(self):
        doc = _claim(claimed_litres=100, claimed_amount=250).insert(ignore_permissions=True)
        self.assertEqual(doc.unit_price_per_litre, 2.5)

    def test_a_claim_with_no_amount_prices_at_zero(self):
        doc = _claim(claimed_amount=0).insert(ignore_permissions=True)
        self.assertEqual(doc.unit_price_per_litre, 0)


class TestFuelClaimConsumption(FrappeTestCase):
    def test_a_vehicle_with_no_ledger_consumed_nothing(self):
        doc = _claim(claimed_litres=100).insert(ignore_permissions=True)
        self.assertEqual(doc.consumed_litres, 0)
        self.assertEqual(doc.variance_litres, 100)

    def test_the_variance_is_the_claim_less_what_the_ledger_holds(self):
        vehicle = _vehicle()
        _ledger(vehicle, 60)
        _ledger(vehicle, 20)
        doc = _claim(vehicle=vehicle, claimed_litres=100).insert(ignore_permissions=True)
        self.assertEqual(doc.consumed_litres, 80)
        self.assertEqual(doc.variance_litres, 20)


class TestFuelClaimApproval(FrappeTestCase):
    def test_a_draft_claim_carries_no_reconciliation_date(self):
        doc = _claim().insert(ignore_permissions=True)
        self.assertFalse(doc.reconciled_on)
        self.assertFalse(doc.approved_by)

    def test_reconciling_stamps_the_reconciliation_date(self):
        doc = _reconciled()
        self.assertTrue(doc.reconciled_on)
        self.assertFalse(doc.approved_by)

    def test_the_requester_cannot_approve_their_own_claim(self):
        doc = _reconciled()
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Approve")

    def test_a_second_person_approving_is_stamped_as_the_approver(self):
        doc = _reconciled()
        approver = _user_with_role("_T-FCM Fleet Manager", "Fleet Manager")
        frappe.set_user(approver)
        self.addCleanup(frappe.set_user, "Administrator")
        apply_workflow(doc, "Approve")
        self.assertEqual(doc.status, "Approved")
        self.assertEqual(doc.approved_by, approver)


class TestFuelClaimFinancialDefaults(FrappeTestCase):
    def test_a_claim_with_no_company_is_filled_from_the_salis_default(self):
        doc = _claim().insert(ignore_permissions=True)
        self.assertTrue(doc.company)
