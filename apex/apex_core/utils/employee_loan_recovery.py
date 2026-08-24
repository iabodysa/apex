# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import flt, rounded, today
from hrms.payroll.doctype.salary_slip.salary_slip_loan_utils import if_lending_app_installed

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT
from apex.apex_core.utils.employee_recovery import _salary_preview

RECOVERY_LOAN_PRODUCT_NAME = "Vehicle Damage Recovery"


def _cap_percent() -> float:
    return min(
        flt(
            frappe.db.get_single_value("Salis Settings", "employee_advance_recovery_max_percent")
        )
        or MAX_RECOVERY_PERCENT,
        MAX_RECOVERY_PERCENT,
    )

_RECOVERY_LOAN_ACCOUNTS = (
    ("loan_account", "Receivable", "Asset"),
    ("payment_account", "Bank", "Asset"),
    ("disbursement_account", "Bank", "Asset"),
    ("interest_income_account", "Income Account", "Income"),
    ("penalty_income_account", "Income Account", "Income"),
    ("interest_receivable_account", "Receivable", "Asset"),
    ("penalty_receivable_account", "Receivable", "Asset"),
)


def _ensure_recovery_loan_account(company: str, fieldname: str, account_type: str, root_type: str) -> str | None:
    label = fieldname.replace("_", " ").title()
    account_name = f"{RECOVERY_LOAN_PRODUCT_NAME} {label}"
    existing = frappe.db.get_value(
        "Account", {"company": company, "account_name": account_name, "is_group": 0}, "name"
    )
    if existing:
        return existing
    parent = frappe.db.get_value(
        "Account", {"company": company, "is_group": 1, "root_type": root_type}, "name"
    )
    if not parent:
        return None
    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": account_name,
            "parent_account": parent,
            "account_type": account_type,
            "company": company,
            "is_group": 0,
        }
    )
    account.insert(ignore_permissions=True)
    return account.name


@if_lending_app_installed
def ensure_recovery_loan_product(company: str) -> str | None:
    abbr = frappe.db.get_value("Company", company, "abbr") or company
    product_code = f"{RECOVERY_LOAN_PRODUCT_NAME} - {abbr}"
    if frappe.db.exists("Loan Product", product_code):
        return product_code

    accounts = {}
    for fieldname, account_type, root_type in _RECOVERY_LOAN_ACCOUNTS:
        account = _ensure_recovery_loan_account(company, fieldname, account_type, root_type)
        if not account:
            return None
        accounts[fieldname] = account

    mode_of_payment = frappe.db.get_value(
        "Mode of Payment", {"type": "Cash"}, "name"
    ) or frappe.db.get_value("Mode of Payment", {}, "name")
    if not mode_of_payment:
        return None

    product = frappe.get_doc(
        {
            "doctype": "Loan Product",
            "company": company,
            "product_code": product_code,
            "product_name": product_code,
            "is_term_loan": 1,
            "repayment_schedule_type": "Monthly as per repayment start date",
            "rate_of_interest": 0,
            "mode_of_payment": mode_of_payment,
            "min_auto_closure_tolerance_amount": -1,
            "max_auto_closure_tolerance_amount": 1,
            "min_days_bw_disbursement_first_repayment": 0,
            **accounts,
        }
    )
    product.insert(ignore_permissions=True)
    return product.name


@if_lending_app_installed
def raise_recovery_loan(
    source_doctype: str,
    source_name: str,
    employee: str,
    amount: float,
    purpose: str,
    company: str | None = None,
    posting_date: str | None = None,
    agreed_installment: float = 0.0,
) -> str | None:
    logger = frappe.logger()
    amount = flt(amount)
    if not (employee and amount > 0):
        return None

    company = company or frappe.db.get_value("Employee", employee, "company")
    if not company:
        logger.warning(
            f"employee_loan_recovery: {source_doctype} {source_name} — employee {employee} "
            "has no company. No Loan raised."
        )
        return None

    loan_product = ensure_recovery_loan_product(company)
    if not loan_product:
        logger.warning(
            f"employee_loan_recovery: {source_doctype} {source_name} — company {company} is "
            "missing an account or Mode of Payment the recovery Loan Product needs. No Loan raised."
        )
        return None

    posting_date = posting_date or today()
    preview, _assignment = _salary_preview(employee, posting_date)
    if not preview:
        logger.warning(
            f"employee_loan_recovery: {source_doctype} {source_name} — no active Salary "
            f"Structure Assignment for {employee}. No Loan raised."
        )
        return None

    cap = round(flt(getattr(preview, "gross_pay", 0)) * _cap_percent() / 100.0, 2)
    if cap <= 0:
        logger.warning(
            f"employee_loan_recovery: {source_doctype} {source_name} — {employee}'s gross pay "
            "leaves no statutory room for an installment. No Loan raised."
        )
        return None

    target = flt(agreed_installment) if flt(agreed_installment) > 0 else amount
    monthly_repayment_amount = round(min(target, cap, amount), 2)
    if monthly_repayment_amount <= 0:
        return None

    loan = frappe.get_doc(
        {
            "doctype": "Loan",
            "applicant_type": "Employee",
            "applicant": employee,
            "company": company,
            "loan_product": loan_product,
            "posting_date": posting_date,
            "loan_amount": amount,
            "rate_of_interest": 0,
            "is_term_loan": 1,
            "repayment_method": "Repay Fixed Amount per Period",
            "monthly_repayment_amount": monthly_repayment_amount,
            "repayment_start_date": posting_date,
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
            "company": company,
            "disbursement_date": posting_date,
            "posting_date": posting_date,
            "disbursed_amount": amount,
        }
    )
    disbursement.insert(ignore_permissions=True)
    disbursement.submit()

    logger.info(
        f"employee_loan_recovery: Loan {loan.name} raised for {source_doctype} {source_name}."
    )
    return loan.name


def _is_recovery_loan_product(loan_product: str | None) -> bool:
    return bool(loan_product) and loan_product.startswith(f"{RECOVERY_LOAN_PRODUCT_NAME} - ")


@if_lending_app_installed
def cap_loan_installments_to_current_pay(doc, method=None) -> None:
    cap = round(flt(doc.gross_pay) * _cap_percent() / 100.0, 2)
    changed = False

    for row in doc.get("loans", []) or []:
        if not row.loan:
            continue
        loan_product = frappe.db.get_value("Loan", row.loan, "loan_product")
        if not _is_recovery_loan_product(loan_product):
            continue

        current = flt(row.total_payment)
        if current <= cap or current <= 0:
            continue

        ratio = cap / current
        row.principal_amount = round(flt(row.principal_amount) * ratio, 2)
        row.interest_amount = round(flt(row.interest_amount) * ratio, 2)
        row.total_payment = round(row.principal_amount + row.interest_amount, 2)
        changed = True
        frappe.logger().warning(
            f"employee_loan_recovery: Loan {row.loan} installment reduced from "
            f"{current} to {row.total_payment} on {doc.doctype} {doc.name or '(new)'} "
            f"— {doc.employee}'s gross pay this period leaves less statutory room "
            "than when the Loan was raised."
        )

    if not changed:
        return

    doc.total_principal_amount = sum(flt(row.principal_amount) for row in doc.get("loans", []))
    doc.total_interest_amount = sum(flt(row.interest_amount) for row in doc.get("loans", []))
    doc.total_loan_repayment = sum(flt(row.total_payment) for row in doc.get("loans", []))
    doc.net_pay = flt(doc.gross_pay) - (flt(doc.total_deduction) + flt(doc.total_loan_repayment))
    doc.rounded_total = rounded(doc.net_pay)
    doc.base_net_pay = flt(flt(doc.net_pay) * flt(doc.exchange_rate), doc.precision("base_net_pay"))
    doc.base_rounded_total = flt(rounded(doc.base_net_pay), doc.precision("base_net_pay"))
