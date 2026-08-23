# Copyright (c) 2026, afmcoltd
"""Employee cost recovery on the native lending app's Loan.

The lending app was installed at the owner's instruction; ``hrms`` wires a Loan into
payroll on its own the moment it finds one (``if_lending_app_installed``,
hrms/payroll/doctype/salary_slip/salary_slip_loan_utils.py:13-21). Its
``set_loan_repayment`` (salary_slip_loan_utils.py:25) reads every submitted, open Loan
with ``repay_from_salary`` set for the Salary Slip's own employee and company
(salary_slip_loan_utils.py:74-93), appends its due installment to the slip's ``loans``
child table, and ``make_loan_repayment_entry``/``cancel_loan_repayment_entry``
(:127, :166) post and reverse the matching Loan Repayment on submit and cancel. None of
that is called from here: this module only builds the Loan and lets HRMS run it.

A vehicle damage recovery owes the company money the employee was never given, unlike
Employee Advance (a receivable FOR money the company gave), which is why this module
raises a Loan instead of a second call into ``employee_recovery.raise_recovery_advance``.
Proven empirically (a submitted term Loan with no Loan Disbursement produced zero
accrual and an empty Salary Slip ``loans`` row): ``lending`` will not run a term Loan's
repayment schedule until it is disbursed —
``loan_disbursement.py:26-48`` (``LoanDisbursement.on_submit`` /
``update_repayment_schedule_status``) is the ONLY place a Loan Repayment Schedule moves
from ``Initiated`` to ``Active``, and ``process_loan_interest_accrual.py:69-73``
(``term_loan_accrual_pending``) only looks at the ``Active`` schedule. So this module
disburses the full amount right after the Loan is submitted, into a dedicated internal
clearing pair (``_RECOVERY_LOAN_ACCOUNTS``) rather than the company's real bank account:
the debt is real and the schedule must be Active for HRMS to run it, but no cash
actually left the company, so the "Bank" leg of the disbursement is a same-company
clearing account created and named for this recovery product alone, never a shared
operating account another payment would also post through.

The installment is capped, once, at ``MAX_RECOVERY_PERCENT`` of the employee's own
gross pay (the same KSA Labor Law Art. 91 ceiling ``employee_recovery`` enforces every
period) using one native Salary Slip preview taken when the Loan is built
(``employee_recovery._salary_preview``, reused rather than duplicated — a second real
consumer of that helper). Unlike ``employee_recovery.compute_recovery_installment``,
this cap is NOT re-checked every pay period: a Loan's repayment schedule is fixed at
submit, so the number the employee's gross pay implied on the day the incident was
approved is what every future installment charges, even if pay later falls. The backstop
that stays live every period is native and not ours: Salary Slip's own ``on_submit``
refuses outright when the slip's net pay would go negative
(hrms/payroll/doctype/salary_slip/salary_slip.py:207-209) — a whole slip is blocked
rather than an installment silently shrunk, so payroll must resolve the conflict by
hand instead of the deduction quietly not being collected.

No custom field two-way links a Loan back to its Vehicle Incident (the retired
Employee Advance path had ``custom_source_doctype``/``custom_source_document`` via a
Customization fixture; adding one to Loan is a fixture write outside this change). The
one-way link lives on Vehicle Incident's own ``recovery_loan`` (``no_copy``): raising is
idempotent because the caller only calls this while that field is still blank, exactly
the same guarantee ``recovery_advance`` gave the retired path within one document's
lifecycle.

Raising is NOT gated behind Salis Settings the way wage deduction used to be: once a
Loan is submitted with ``repay_from_salary`` set, HRMS deducts on every Salary Slip it
touches unconditionally — there is no separate "recovery enabled" switch in the native
wiring to defer to, so gating this module's own call would only hide the receivable
without changing what payroll does with it.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, today

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT
from apex.apex_core.utils.employee_recovery import _salary_preview

RECOVERY_LOAN_PRODUCT_NAME = "Vehicle Damage Recovery"

# (fieldname on Loan Product, Account.account_type, Account.root_type)
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
    """Find-or-create ONE of this recovery product's own dedicated accounts.

    Looked up by its own name, never by "any existing account of this type": the
    Bank-typed pair (``payment_account``/``disbursement_account``) exists only to let
    ``lending`` activate a Loan's repayment schedule (see the module docstring), and
    reusing whatever real bank account a company already has of that type would book a
    damage claim's paper disbursement through the account real cash moves through.
    """
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


def ensure_recovery_loan_product(company: str) -> str | None:
    """Return the company's zero-interest Loan Product for damage recovery, creating it once.

    Every account a Loan Product requires (``_RECOVERY_LOAN_ACCOUNTS``) is created
    lazily the first time a company raises a recovery, the same "make Setup Wizard
    finish" reasoning ``ensure_advance_account`` already applies to the Employee Advance
    account: demanding an accountant configure a Loan Product before the first
    submittable damage claim would make the operational document unsubmittable on a
    fresh site. ``product_code`` (the Loan Product's own name) is scoped by the
    company's abbreviation so more than one company can each raise this Loan Product.
    """
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
            "product_name": RECOVERY_LOAN_PRODUCT_NAME,
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
    """Raise the submitted, undisbursed term Loan recovering ``amount`` from ``employee``.

    Returns the Loan name, or ``None`` — logging why, never throwing — when the site
    cannot yet size an installment: no company, no accounts a Loan Product needs, or no
    active Salary Structure Assignment to read a gross pay from. A damage recovery
    cannot be posted with a repayment schedule that has no wage to be a percentage of,
    so unlike ``employee_recovery.raise_recovery_advance`` (which raises the receivable
    unconditionally and only defers the deduction), this defers the receivable itself;
    the incident stays the event of record and ``recovery_loan`` stays blank until
    payroll is configured for the employee.
    """
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

    cap = round(flt(getattr(preview, "gross_pay", 0)) * MAX_RECOVERY_PERCENT / 100.0, 2)
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
