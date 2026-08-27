# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.company import company_for_vehicle
from apex.tests.factories import make_rental_office

_PERIOD = "2026-04"


def _office(label="_T-RS Office"):
    return make_rental_office(label + " " + frappe.generate_hash(length=6))


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-RS " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _user_with_role(first_name, role):
    email = "_t_rs_" + frappe.generate_hash(length=6) + "@example.com"
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


def _accrual(office, vehicle, amount, accrual_date=_PERIOD + "-10"):
    return frappe.get_doc(
        {
            "doctype": "Rental Accrual Ledger",
            "vehicle": vehicle,
            "rental_office": office,
            "company": company_for_vehicle(vehicle),
            "accrual_date": accrual_date,
            "amount": amount,
            "source_doctype": "Rental Vehicle Movement",
        }
    ).insert(ignore_permissions=True).name


def _line(vehicle, days=10, daily_rate=150, **overrides):
    row = {"vehicle": vehicle, "days": days, "daily_rate": daily_rate}
    row.update(overrides)
    return row


def _settlement(office=None, **overrides):
    fields = {
        "doctype": "Rental Settlement",
        "rental_office": office or _office(),
        "period_month": _PERIOD,
        "claimed_total": 1500,
        "status": "Draft",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _reconciled(**overrides):
    doc = _settlement(**overrides).insert(ignore_permissions=True)
    apply_workflow(doc, "Reconcile")
    return doc


class TestRentalSettlementOnePerOfficePerPeriod(FrappeTestCase):
    def test_a_second_settlement_for_the_same_office_and_period_is_refused(self):
        office = _office()
        _settlement(office).insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "already covers office"):
            _settlement(office).insert(ignore_permissions=True)

    def test_the_same_office_in_another_period_is_accepted(self):
        office = _office()
        _settlement(office).insert(ignore_permissions=True)
        doc = _settlement(office, period_month="2026-05").insert(ignore_permissions=True)
        self.assertEqual(doc.period_month, "2026-05")

    def test_another_office_in_the_same_period_is_accepted(self):
        _settlement().insert(ignore_permissions=True)
        doc = _settlement().insert(ignore_permissions=True)
        self.assertEqual(doc.period_month, _PERIOD)


class TestRentalSettlementAccruedTotal(FrappeTestCase):
    def test_the_lines_decide_the_accrued_total_when_lines_are_present(self):
        doc = _settlement(vehicles=[_line(_vehicle(), days=10, daily_rate=150)]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.accrued_total, 1500)
        self.assertEqual(doc.accrued_from_ledger, 0)

    def test_a_line_amount_is_derived_from_the_days_and_the_rate(self):
        doc = _settlement(vehicles=[_line(_vehicle(), days=4, daily_rate=25)]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.vehicles[0].amount, 100)

    def test_the_ledger_decides_the_accrued_total_when_no_line_is_present(self):
        office, vehicle = _office(), _vehicle()
        _accrual(office, vehicle, 700)
        doc = _settlement(office).insert(ignore_permissions=True)
        self.assertEqual(doc.accrued_total, 700)
        self.assertEqual(doc.accrued_from_ledger, 1)

    def test_a_reversed_accrual_is_left_out_of_the_ledger_total(self):
        office, vehicle = _office(), _vehicle()
        original = _accrual(office, vehicle, 700)
        frappe.get_doc(
            {
                "doctype": "Rental Accrual Ledger",
                "vehicle": vehicle,
                "rental_office": office,
                "company": company_for_vehicle(vehicle),
                "accrual_date": _PERIOD + "-10",
                "amount": -700,
                "source_doctype": "Rental Vehicle Movement",
                "reversal_of": original,
            }
        ).insert(ignore_permissions=True)
        doc = _settlement(office).insert(ignore_permissions=True)
        self.assertEqual(doc.ledger_accrued_total, 700)

    def test_an_accrual_outside_the_period_is_left_out(self):
        office, vehicle = _office(), _vehicle()
        _accrual(office, vehicle, 700, accrual_date="2026-05-10")
        doc = _settlement(office).insert(ignore_permissions=True)
        self.assertEqual(doc.ledger_accrued_total, 0)


class TestRentalSettlementVariance(FrappeTestCase):
    def test_the_variance_is_the_claim_less_what_was_accrued(self):
        doc = _settlement(
            claimed_total=2000, vehicles=[_line(_vehicle(), days=10, daily_rate=150)]
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.variance, 500)

    def test_the_ledger_variance_is_the_accrual_less_the_ledger(self):
        office, vehicle = _office(), _vehicle()
        _accrual(office, vehicle, 1000)
        doc = _settlement(
            office, vehicles=[_line(vehicle, days=10, daily_rate=150)]
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.ledger_variance, 500)


class TestRentalSettlementTax(FrappeTestCase):
    def test_the_tax_is_taken_on_the_claimed_total(self):
        doc = _settlement(claimed_total=1000, tax_rate=15).insert(ignore_permissions=True)
        self.assertEqual(doc.tax_amount, 150)
        self.assertEqual(doc.grand_total, 1150)

    def test_a_settlement_that_names_no_rate_carries_the_declared_default(self):
        doc = _settlement(claimed_total=1000).insert(ignore_permissions=True)
        self.assertEqual(doc.tax_rate, 15)
        self.assertEqual(doc.tax_amount, 150)

    def test_an_explicit_zero_rate_is_taxed_at_zero(self):
        doc = _settlement(claimed_total=1000, tax_rate=0).insert(ignore_permissions=True)
        self.assertEqual(doc.tax_amount, 0)
        self.assertEqual(doc.grand_total, 1000)


class TestRentalSettlementApproval(FrappeTestCase):
    def test_a_settlement_with_no_requester_names_the_session_user(self):
        doc = _settlement().insert(ignore_permissions=True)
        self.assertEqual(doc.requested_by, frappe.session.user)

    def test_a_settlement_short_of_approval_names_no_approver(self):
        doc = _reconciled()
        self.assertFalse(doc.approved_by)
        self.assertFalse(doc.approved_on)

    def test_the_requester_cannot_approve_their_own_settlement(self):
        doc = _reconciled()
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Approve")

    def test_a_second_person_approving_is_stamped_as_the_approver(self):
        doc = _reconciled()
        approver = _user_with_role("_T-RS Fleet Manager", "Fleet Manager")
        frappe.set_user(approver)
        self.addCleanup(frappe.set_user, "Administrator")
        apply_workflow(doc, "Approve")
        self.assertEqual(doc.status, "Approved")
        self.assertEqual(doc.approved_by, approver)
        self.assertTrue(doc.approved_on)


class TestRentalSettlementCompany(FrappeTestCase):
    def test_a_settlement_with_no_company_is_filled_from_the_salis_default(self):
        doc = _settlement().insert(ignore_permissions=True)
        self.assertTrue(doc.company)
