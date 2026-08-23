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
consumer of that helper).

WHY THAT ALONE IS NOT ENOUGH, checked against the installed primitive rather than
assumed: ``lending`` never re-evaluates a term Loan's installment against a
borrower's ACTUAL pay. A schedule's rows are computed once, in
``loan_repayment_schedule.py:30-96`` (``make_repayment_schedule``), and are only
rebuilt by ``validate()`` on the schedule document ITSELF — which a submitted Loan
never calls again (``loan.py:173-191``, ``update_draft_schedule`` only runs
pre-submission). Every later read — ``calculate_amounts`` /
``get_amounts`` (loan_repayment.py:1128-1226) via ``set_loan_repayment``
(salary_slip_loan_utils.py:25-71) — walks those SAME frozen rows through the
period's ``Loan Interest Accrual`` entries; none of it looks at the employee's
current gross pay. The one native primitive that reshapes a live Loan's future
installments is ``Loan Restructure`` (loan_restructure.py), which is a
human-reviewed collections document (branch limits, waivers, DPD, an
initiated-restructure guard) built for a case worker's decision, not a silent
per-slip recompute — driving one automatically on every Salary Slip would itself
route around the review it is supposed to get. So this module's frozen figure IS a
real gap: an employee whose pay drops after the Loan is raised keeps owing the
ORIGINAL installment, and nothing in ``lending`` shrinks it back down.

The backstop that DOES stay live every period is native and not ours: Salary Slip's
own ``on_submit`` refuses outright when the slip's net pay would go negative
(hrms/payroll/doctype/salary_slip/salary_slip.py:207-209). That is a materially
weaker promise than "no more than half of THIS period's pay" — it only refuses the
slip once pay has gone NEGATIVE, so an installment can legally consume the vast
majority of a shrunken paycheque and still submit without a word.

``cap_loan_installments_to_current_pay`` closes that gap on the SALARY SLIP side —
never by touching the Loan or its schedule (which would fight the accrual/repayment
bookkeeping ``loan_repayment.py`` owns): it re-reads ``doc.gross_pay`` (THIS slip's
own, already computed) right after hrms first populates ``doc.loans`` and clamps
this slip's own row, never the Loan, down to the current cap when the frozen
installment would exceed it. The unpaid remainder is not written off: ``lending``'s
own accrual math (loan_repayment.py's outstanding-balance read in
``get_amounts``) already treats an underpaid accrual entry as still owed, so it
surfaces again the next time this Loan is read — carried forward exactly the way a
partial repayment always is, not lost. The seam is Salary Slip's own ``validate``
doc_event — NOT ``before_validate``: ``set_loan_repayment`` only populates
``doc.loans``/``doc.net_pay`` INSIDE the controller's own ``validate()``
(salary_slip.py:169, via ``calculate_net_pay`` at :853), so a ``before_validate``
handler would run too early and see nothing to clamp; a handler registered on
``validate`` itself runs AFTER the controller's own method returns
(frappe/model/document.py's ``hook``/``compose`` chain), which is the first point a
row exists. Reached ONLY through a ``hooks.py`` ``doc_events`` entry — this module
cannot add one (out of this change's write scope; a `hooks.py` edit is reported, not
applied), so the function is written, tested by direct call, and NOT YET ACTIVE
until that one line is added. See the exact patch in the card.

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


def _is_recovery_loan_product(loan_product: str | None) -> bool:
    """True only for a Loan Product THIS module raised, never a company's own staff loan.

    Scoping on the product (rather than "any Loan with repay_from_salary") matters
    the moment Apex or HR raises a Loan for something else — a real salary advance a
    person asked for should not be capped by a rule written for a damage claim they
    did not choose.
    """
    return bool(loan_product) and loan_product.startswith(f"{RECOVERY_LOAN_PRODUCT_NAME} - ")


def cap_loan_installments_to_current_pay(doc, method=None) -> None:
    """Reduce (never increase) each recovery Loan row on THIS slip to at most
    ``MAX_RECOVERY_PERCENT`` of THIS period's own gross pay, and recompute the
    totals hrms derived from it.

    Wire this as Salary Slip's own ``validate`` doc_event, NOT ``before_validate``:
    ``set_loan_repayment`` (salary_slip_loan_utils.py:25, called from
    ``calculate_net_pay`` at salary_slip.py:853) is what first populates
    ``doc.loans`` and ``doc.net_pay``, and that call happens INSIDE the
    controller's own ``validate()`` (salary_slip.py:169) — before ``before_validate``
    would ever see a populated row. A ``doc_events`` handler registered on
    ``validate`` runs AFTER the controller's own ``validate()`` method completes
    (frappe/model/document.py's ``hook``/``compose``: the class method runs first,
    every registered hook after), which is the first point this row exists to clamp.

    Because nothing runs ``set_net_pay`` (salary_slip.py:860-870) again after this,
    the same formula is repeated here for ``total_loan_repayment``, ``net_pay``,
    ``rounded_total``, ``base_net_pay`` and ``base_rounded_total`` — the only fields
    that formula derives from ``total_loan_repayment``, which is the one number this
    function changes.
    """
    from frappe.utils import rounded

    cap = round(flt(doc.gross_pay) * MAX_RECOVERY_PERCENT / 100.0, 2)
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
