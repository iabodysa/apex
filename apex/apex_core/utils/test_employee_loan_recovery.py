# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.payroll.doctype.salary_slip.test_salary_slip import make_holiday_list
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
from hrms.payroll.doctype.salary_structure.test_salary_structure import make_salary_structure

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT
from apex.apex_core.utils.employee_loan_recovery import (
    ensure_recovery_loan_product,
    raise_recovery_loan,
)
from apex.apex_core.utils.employee_recovery import _salary_preview

_COMPANY = "_Test Company"

requires_lending = unittest.skipUnless(
    "lending" in frappe.get_installed_apps(),
    "the lending app is not installed on this site, so there is no Loan wiring to prove",
)
"""Every class here asserts what hrms does with a real Loan, and apex declares only
frappe, erpnext and hrms — so a site without lending has no Loan DocType at all. On such
a site these skip by name; the module they cover returns ``None`` there rather than
raising, which is what ``if_lending_app_installed`` is for."""


def _company_holiday_list() -> None:
    if frappe.get_cached_value("Company", _COMPANY, "default_holiday_list"):
        return
    frappe.db.set_value("Company", _COMPANY, "default_holiday_list", make_holiday_list())


def _payroll_employee(email: str, base: float) -> tuple[str, str]:
    _company_holiday_list()
    employee = make_employee(email, company=_COMPANY)
    struct_name = f"Apex Recovery Proof {email}"
    if frappe.db.exists("Salary Structure", struct_name):
        frappe.db.delete("Salary Structure", struct_name)
    currency = frappe.get_cached_value("Company", _COMPANY, "default_currency")
    structure = make_salary_structure(
        struct_name, "Monthly", employee=employee, company=_COMPANY, base=base, currency=currency
    )
    return employee, structure.name


def _build_slip(structure, employee):
    slip = make_salary_slip(structure, employee=employee, posting_date=nowdate())
    slip.get_emp_and_working_day_details()
    return slip


def _submit_without_emailing(slip):
    previous = frappe.flags.via_payroll_entry
    frappe.flags.via_payroll_entry = True
    try:
        slip.submit()
    finally:
        frappe.flags.via_payroll_entry = previous


@requires_lending
class TestEnsureRecoveryLoanProduct(FrappeTestCase):
    def test_the_product_is_zero_interest_term_and_reused(self):
        first = ensure_recovery_loan_product(_COMPANY)
        second = ensure_recovery_loan_product(_COMPANY)
        self.assertEqual(first, second)
        product = frappe.get_doc("Loan Product", first)
        self.assertEqual(product.rate_of_interest, 0)
        self.assertTrue(product.is_term_loan)


@requires_lending
class TestRaiseRecoveryLoan(FrappeTestCase):
    def test_defers_without_an_active_salary_structure_assignment(self):
        employee = make_employee("apex.loan.defer@apex.test", company=_COMPANY)
        frappe.db.delete("Salary Structure Assignment", {"employee": employee})
        result = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-DEFER-0001",
            employee=employee,
            amount=500,
            purpose="test",
            company=_COMPANY,
        )
        self.assertIsNone(result)

    def test_the_installment_is_capped_at_the_statutory_percentage_of_gross_pay(self):
        employee, _structure = _payroll_employee("apex.loan.cap@apex.test", base=1000)
        preview, _assignment = _salary_preview(employee, nowdate())
        expected_cap = round(preview.gross_pay * MAX_RECOVERY_PERCENT / 100.0, 2)

        loan_name = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-CAP-0001",
            employee=employee,
            amount=5000,
            purpose="test",
            company=_COMPANY,
            agreed_installment=5000,
        )
        self.assertIsNotNone(loan_name)
        loan = frappe.get_doc("Loan", loan_name)
        self.assertEqual(loan.monthly_repayment_amount, expected_cap)
        self.assertLess(loan.monthly_repayment_amount, 5000)

    def test_the_operators_own_narrower_cap_is_honoured(self):
        settings = frappe.get_single("Salis Settings")
        restore = settings.employee_advance_recovery_max_percent
        settings.employee_advance_recovery_max_percent = 25
        settings.save(ignore_permissions=True)
        self.addCleanup(frappe.db.set_single_value, "Salis Settings", "employee_advance_recovery_max_percent", restore)

        employee, _structure = _payroll_employee("apex.loan.narrow@apex.test", base=1000)
        preview, _assignment = _salary_preview(employee, nowdate())
        narrowed = round(preview.gross_pay * 25 / 100.0, 2)
        statutory = round(preview.gross_pay * MAX_RECOVERY_PERCENT / 100.0, 2)

        loan_name = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-NARROW-0001",
            employee=employee,
            amount=5000,
            purpose="test",
            company=_COMPANY,
            agreed_installment=5000,
        )
        loan = frappe.get_doc("Loan", loan_name)
        self.assertEqual(loan.monthly_repayment_amount, narrowed)
        self.assertLess(narrowed, statutory)

    def test_an_installment_inside_the_cap_is_taken_as_agreed(self):
        employee, _structure = _payroll_employee("apex.loan.agreed@apex.test", base=8000)
        loan_name = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-AGREED-0001",
            employee=employee,
            amount=1200,
            purpose="test",
            company=_COMPANY,
            agreed_installment=300,
        )
        loan = frappe.get_doc("Loan", loan_name)
        self.assertEqual(loan.monthly_repayment_amount, 300)
        self.assertEqual(loan.applicant, employee)
        self.assertEqual(loan.repay_from_salary, 1)


@requires_lending
class TestSalarySlipLoanProof(FrappeTestCase):

    def test_a_real_salary_slip_carries_the_loans_native_installment(self):
        employee, structure = _payroll_employee("apex.loan.proof@apex.test", base=8000)
        loan_name = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-PROOF-0001",
            employee=employee,
            amount=1200,
            purpose="test",
            company=_COMPANY,
            posting_date=nowdate(),
            agreed_installment=300,
        )
        self.assertIsNotNone(loan_name)

        slip = _build_slip(structure, employee)
        slip.insert()
        _submit_without_emailing(slip)

        self.assertEqual(len(slip.loans), 1)
        loan_row = slip.loans[0]
        self.assertEqual(loan_row.loan, loan_name)
        self.assertEqual(loan_row.total_payment, 300)
        self.assertEqual(slip.total_loan_repayment, 300)
        self.assertEqual(
            slip.net_pay, slip.gross_pay - slip.total_deduction - slip.total_loan_repayment
        )


@requires_lending
class TestNoNegativeNetSalaryFromALoan(FrappeTestCase):

    def test_an_installment_within_net_pay_submits(self):
        employee, structure = _payroll_employee("apex.loan.floor.ok@apex.test", base=8000)
        raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-FLOOR-OK-0001",
            employee=employee,
            amount=1200,
            purpose="test",
            company=_COMPANY,
            agreed_installment=300,
        )
        slip = _build_slip(structure, employee)
        slip.insert()
        _submit_without_emailing(slip)
        self.assertGreaterEqual(slip.net_pay, 0)

    def test_an_installment_that_would_go_negative_is_capped_before_it_can(self):
        employee, structure = _payroll_employee("apex.loan.floor.refuse@apex.test", base=500)
        loan_product = ensure_recovery_loan_product(_COMPANY)
        loan = frappe.get_doc(
            {
                "doctype": "Loan",
                "applicant_type": "Employee",
                "applicant": employee,
                "company": _COMPANY,
                "loan_product": loan_product,
                "posting_date": nowdate(),
                "loan_amount": 10000,
                "rate_of_interest": 0,
                "is_term_loan": 1,
                "repayment_method": "Repay Fixed Amount per Period",
                "monthly_repayment_amount": 10000,
                "repayment_start_date": nowdate(),
                "repay_from_salary": 1,
            }
        )
        loan.insert(ignore_permissions=True)
        loan.submit()
        disbursement = frappe.get_doc(
            {
                "doctype": "Loan Disbursement",
                "against_loan": loan.name,
                "applicant_type": "Employee",
                "applicant": employee,
                "company": _COMPANY,
                "disbursement_date": nowdate(),
                "posting_date": nowdate(),
                "disbursed_amount": 10000,
            }
        )
        disbursement.insert(ignore_permissions=True)
        disbursement.submit()

        slip = _build_slip(structure, employee)
        slip.insert()

        cap = round(slip.gross_pay * MAX_RECOVERY_PERCENT / 100.0, 2)
        self.assertEqual(
            slip.loans[0].total_payment,
            cap,
            "a 10,000 installment on a 500 base was not clamped — check the Salary "
            "Slip validate hook is still wired in hooks.py",
        )
        self.assertGreaterEqual(slip.net_pay, 0)

        _submit_without_emailing(slip)
        self.assertEqual(slip.docstatus, 1)


@requires_lending
class TestCapLoanInstallmentsToCurrentPay(FrappeTestCase):

    def test_a_pay_drop_below_the_frozen_installment_is_absorbed_not_gutted(self):
        employee, structure = _payroll_employee("apex.loan.paydrop@apex.test", base=6000)
        loan_name = raise_recovery_loan(
            source_doctype="Vehicle Incident",
            source_name="VI-PAYDROP-0001",
            employee=employee,
            amount=999999,
            purpose="test",
            company=_COMPANY,
        )
        loan = frappe.get_doc("Loan", loan_name)
        frozen_installment = loan.monthly_repayment_amount
        self.assertGreater(frozen_installment, 0)

        assignment = frappe.db.get_value(
            "Salary Structure Assignment", {"employee": employee}, "name"
        )
        frappe.db.set_value("Salary Structure Assignment", assignment, "base", 100)

        slip = _build_slip(structure, employee)
        slip.insert()

        self.assertEqual(len(slip.loans), 1)
        new_cap = round(slip.gross_pay * MAX_RECOVERY_PERCENT / 100.0, 2)
        self.assertLess(new_cap, frozen_installment)

        self.assertEqual(
            slip.loans[0].total_payment,
            new_cap,
            "the frozen installment was not clamped to this period's pay — "
            "check the Salary Slip validate hook is still wired in hooks.py",
        )
        self.assertGreater(slip.net_pay, slip.gross_pay - frozen_installment)
        self.assertAlmostEqual(
            slip.net_pay, slip.gross_pay - slip.total_deduction - new_cap, places=2
        )
        self.assertGreaterEqual(slip.net_pay, slip.gross_pay * 0.4)

        _submit_without_emailing(slip)
        self.assertEqual(slip.docstatus, 1)
