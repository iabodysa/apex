# Copyright (c) 2026, afmcoltd
"""Employee cost recovery on the native HRMS Employee Advance chain.

Native primitive, no bespoke DocType. An operational loss recovered from a worker
is exactly what HRMS already models:

    Employee Advance          the receivable the worker owes the company. Carries
                              the balance (``advance_amount`` / ``paid_amount`` /
                              ``return_amount``) that a one-shot deduction cannot.
    Journal / Payment Entry   the company payment, raised ONLY through HRMS's own
                              ``employee_advance.make_bank_entry`` button. This
                              module posts NO GL, Journal or Payment Entry — there
                              is exactly one employee-advance accounting path and
                              it is HRMS's.
    Additional Salary         one installment, ``ref_doctype``/``ref_docname``
                              pointed at the advance. HRMS's own
                              ``update_return_amount_in_employee_advance`` moves
                              ``return_amount`` on submit and reverses it on
                              cancel, so the recovered balance is maintained
                              natively — never recomputed here.

This module only decides WHETHER and HOW MUCH. The deduction side is gated by
Salis Settings and is OFF by default, so no wage is touched until Accounts and
Payroll configure the native recovery Salary Component. Raising the
receivable is NOT policy-gated — an advance is a lawful receivable regardless; only
its recovery from wages is capped by KSA Labor Law Art. 91.

Recovery is predicated on the company having actually paid: outstanding is measured
from ``paid_amount``, which only the native payment entry sets. Nothing is deducted
from a wage for money the company never disbursed.

Source linkage is two-way and duplicate-safe: the source row is locked before the
existing-link check and insert, and the source document keeps its own
``Employee Advance`` link, and the advance carries ``custom_source_doctype`` /
``custom_source_document`` (Customization shipped in apex_core/custom/employee_advance.json),
so "one source document maps to at most one advance" survives an amendment on
either side.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, get_first_day, get_last_day, getdate, today
from hrms.hr.doctype.employee_advance import employee_advance as native_employee_advance

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT

SOURCE_DOCTYPE_FIELD = "custom_source_doctype"
SOURCE_DOCNAME_FIELD = "custom_source_document"

OPEN_ADVANCE_STATUSES = ("Unpaid", "Paid", "Partly Claimed and Returned")


def _source_link_available() -> bool:
    """True once the Employee Advance customization has synced (post-migrate)."""
    return frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD)


def find_recovery_advance(source_doctype: str, source_name: str) -> str | None:
    """The non-cancelled Employee Advance already raised for a source document.

    The "maps once" guarantee: keyed on the advance itself, so it holds even when
    the source document is amended (an amendment starts with a blank no_copy link).
    """
    if not (source_name and _source_link_available()):
        return None
    return frappe.db.get_value(
        "Employee Advance",
        {
            SOURCE_DOCTYPE_FIELD: source_doctype,
            SOURCE_DOCNAME_FIELD: source_name,
            "docstatus": ["<", 2],
        },
        "name",
    )


def raise_recovery_advance(
    source_doctype: str,
    source_name: str,
    employee: str,
    amount: float,
    purpose: str,
    company: str | None = None,
    posting_date: str | None = None,
) -> str | None:
    """Raise (once) the submitted Employee Advance recovering ``amount`` from ``employee``.

    Returns the advance name, or the pre-existing one when this source document has
    already been mapped. Returns ``None`` — logging why, never throwing — when the
    site is not configured for employee advances yet (no company, no Employee
    Advance account); the operational document must still be submittable on a site
    whose Accounts setup is incomplete.

    The advance account is checked to be of type Receivable before the Employee Advance
    is built: HRMS requires a Receivable advance account and throws on submit, so
    catching it here degrades to a logged warning instead of a failed submit.
    """
    logger = frappe.logger()
    amount = flt(amount)
    if not (employee and amount > 0):
        return None

    if not _source_link_available():
        logger.warning(
            f"employee_recovery: {source_doctype} {source_name} — the Employee Advance source "
            f"Customization has not synced yet (run bench migrate). No Employee Advance raised."
        )
        return None

    if not frappe.db.get_value(
        source_doctype, source_name, "name", for_update=True
    ):
        logger.warning(
            f"employee_recovery: source {source_doctype} {source_name} does not exist. "
            "No Employee Advance raised."
        )
        return None

    existing = find_recovery_advance(source_doctype, source_name)
    if existing:
        return existing

    company = company or frappe.db.get_value("Employee", employee, "company")
    if not company:
        logger.warning(
            f"employee_recovery: {source_doctype} {source_name} — employee {employee} has no "
            f"company. No Employee Advance raised."
        )
        return None

    advance_account = frappe.db.get_value("Company", company, "default_employee_advance_account")
    if not advance_account:
        logger.warning(
            f"employee_recovery: {source_doctype} {source_name} — company {company} has no Default "
            f"Employee Advance Account. No Employee Advance raised."
        )
        return None

    if frappe.db.get_value("Account", advance_account, "account_type") != "Receivable":
        logger.warning(
            f"employee_recovery: {source_doctype} {source_name} — advance account {advance_account} "
            f"is not of type Receivable. No Employee Advance raised."
        )
        return None

    advance = frappe.get_doc(
        {
            "doctype": "Employee Advance",
            "employee": employee,
            "company": company,
            "posting_date": posting_date or today(),
            "purpose": purpose,
            "advance_amount": amount,
            "advance_account": advance_account,
            "currency": frappe.db.get_value("Company", company, "default_currency"),
            "exchange_rate": 1,
            "repay_unclaimed_amount_from_salary": 1,
            SOURCE_DOCTYPE_FIELD: source_doctype,
            SOURCE_DOCNAME_FIELD: source_name,
        }
    )
    advance.insert(ignore_permissions=True)
    advance.submit()
    logger.info(
        f"employee_recovery: Employee Advance {advance.name} raised for {source_doctype} {source_name}."
    )
    return advance.name


def _monthly_wage(employee: str, on_date: str) -> float:
    """The worker's native monthly wage: the ``base`` of the Salary Structure
    Assignment in force on ``on_date``. 0.0 when the worker has no assignment (no
    wage known, so nothing may be deducted)."""
    base = frappe.db.get_value(
        "Salary Structure Assignment",
        {"employee": employee, "docstatus": 1, "from_date": ["<=", on_date]},
        "base",
        order_by="from_date desc",
    )
    return flt(base)


def _scheduled_deductions(employee: str, start: str, end: str) -> float:
    """Deductions already claiming the pay period ``start``..``end`` for a worker.

    Counts drafts as well as submitted rows: a queued installment is money already
    spoken for, so including it is what keeps repeated runs from over-committing the
    same wage.
    """
    rows = frappe.get_all(
        "Additional Salary",
        filters={
            "employee": employee,
            "type": "Deduction",
            "disabled": 0,
            "docstatus": ["<", 2],
        },
        or_filters=[
            ["payroll_date", "between", [start, end]],
            ["is_recurring", "=", 1],
        ],
        fields=["amount", "is_recurring", "from_date", "to_date"],
    )
    total = 0.0
    for row in rows:
        if row.is_recurring:
            if not (row.from_date and row.to_date):
                continue
            if getdate(row.from_date) > getdate(end) or getdate(row.to_date) < getdate(end):
                continue
        total += flt(row.amount)
    return total


def _pending_installments(advance: str) -> float:
    """Installments already queued against an advance but not yet submitted.

    A submitted installment has already moved the advance's ``return_amount``
    natively; a draft has not, so it must be subtracted from the outstanding balance
    by hand or the next run would queue the same money twice.
    """
    queued = frappe.get_all(
        "Additional Salary",
        filters={"ref_doctype": "Employee Advance", "ref_docname": advance, "docstatus": 0},
        pluck="amount",
    )
    return sum(flt(amount) for amount in queued)


def _agreed_installment(source_doctype: str | None, source_name: str | None) -> float:
    """Read the agreement from the linked operational source without duplicating it."""
    if not (source_doctype and source_name):
        return 0.0
    if not frappe.db.exists("DocType", source_doctype):
        return 0.0
    if not frappe.get_meta(source_doctype).has_field("installment_amount"):
        return 0.0
    return flt(frappe.db.get_value(source_doctype, source_name, "installment_amount"))


def bounded_installment(
    outstanding: float, configured_limit: float, agreed: float = 0.0
) -> float:
    """The lowest binding limit on one installment, floored at zero.

    Pure arithmetic, deliberately free of any DB read: ``agreed <= 0`` means "no
    installment agreed" (not "recover nothing"), and either binding limit hitting
    zero defers the whole recovery.
    """
    limits = [flt(outstanding), flt(configured_limit)]
    if flt(agreed) > 0:
        limits.append(flt(agreed))
    return max(round(float(min(limits)), 2), 0.0)


def compute_recovery_installment(advance: str, payroll_date: str | None = None) -> float:
    """SAR recoverable from ONE pay period against ``advance``.

    The lowest of every binding limit, floored at zero:

      * outstanding — what the company actually paid out and has not recovered yet,
        minus installments already queued;
      * the agreed installment recorded on the source document (0 = none agreed);
      * the configured scheduling limit, itself never above 50% of monthly base;
      * known Additional Salary deductions already queued for the same period.

    This scheduler does not calculate the final salary, loan repayments, or every
    Salary Structure deduction. It therefore makes no net-pay guarantee; the draft
    remains subject to native payroll review and calculation.

    0.0 means "recover nothing this period" (policy off, no wage known, balance
    cleared, or the period is fully committed) and the caller must defer, not post.
    """
    payroll_date = payroll_date or today()
    fields = ["employee", "paid_amount", "return_amount", "docstatus"]
    if _source_link_available():
        fields += [SOURCE_DOCTYPE_FIELD, SOURCE_DOCNAME_FIELD]
    advance_doc = frappe.db.get_value("Employee Advance", advance, fields, as_dict=True)
    if not advance_doc or advance_doc.docstatus != 1:
        return 0.0

    outstanding = (
        flt(advance_doc.paid_amount) - flt(advance_doc.return_amount) - _pending_installments(advance)
    )
    if outstanding <= 0:
        return 0.0

    enabled = frappe.db.get_single_value(
        "Salis Settings", "enable_employee_advance_recovery"
    )
    if not enabled:
        return 0.0

    wage = _monthly_wage(advance_doc.employee, payroll_date)
    if wage <= 0:
        return 0.0

    cap_percent = min(
        flt(
            frappe.db.get_single_value(
                "Salis Settings", "employee_advance_recovery_max_percent"
            )
        )
        or MAX_RECOVERY_PERCENT,
        MAX_RECOVERY_PERCENT,
    )
    known_deductions = _scheduled_deductions(
        advance_doc.employee, get_first_day(payroll_date), get_last_day(payroll_date)
    )
    return bounded_installment(
        outstanding=outstanding,
        configured_limit=(wage * cap_percent / 100.0) - known_deductions,
        agreed=_agreed_installment(
            advance_doc.get(SOURCE_DOCTYPE_FIELD),
            advance_doc.get(SOURCE_DOCNAME_FIELD),
        ),
    )


def _recovery_component() -> str | None:
    """Return the configured native deduction component while recovery is enabled."""
    if not frappe.db.get_single_value("Salis Settings", "enable_employee_advance_recovery"):
        return None
    component = frappe.db.get_single_value(
        "Salis Settings", "employee_advance_recovery_component"
    )
    if not component:
        frappe.logger().warning(
            "employee_recovery: Salis Settings has no Recovery Salary Component. "
            "No installment scheduled."
        )
        return None
    if frappe.db.get_value("Salary Component", component, "type") != "Deduction":
        frappe.logger().warning(
            f"employee_recovery: Salary Component {component} is not of type Deduction. "
            f"No installment scheduled."
        )
        return None
    return component


@frappe.whitelist(methods=["POST"])
def schedule_recovery_deduction(advance: str, payroll_date: str | None = None) -> str | None:
    """Queue one draft Additional Salary installment against ``advance``.

    Draft, not submitted: payroll keeps the final say, exactly as the Custody Damage
    Assessment deduction does. Returns the Additional Salary name, or ``None`` when
    recovery is deferred (nothing recoverable this period) or already queued for it.
    """
    advance_doc = frappe.get_doc("Employee Advance", advance, for_update=True)
    frappe.has_permission("Employee Advance", "read", doc=advance_doc, throw=True)
    frappe.has_permission("Additional Salary", "create", throw=True)

    payroll_date = payroll_date or today()
    period_start = get_first_day(payroll_date)
    period_end = get_last_day(payroll_date)

    if frappe.db.exists(
        "Additional Salary",
        {
            "ref_doctype": "Employee Advance",
            "ref_docname": advance,
            "docstatus": ["<", 2],
            "payroll_date": ["between", [period_start, period_end]],
        },
    ):
        return None

    component = _recovery_component()
    if not component:
        return None

    amount = compute_recovery_installment(advance, payroll_date)
    if amount <= 0:
        frappe.logger().info(
            f"employee_recovery: nothing recoverable from advance {advance} for {payroll_date}. Deferred."
        )
        return None

    installment = native_employee_advance.create_return_through_additional_salary(
        advance_doc
    )
    installment.salary_component = component
    installment.amount = amount
    installment.payroll_date = payroll_date
    installment.overwrite_salary_structure_amount = 0
    installment.insert(ignore_permissions=True)
    frappe.logger().info(
        f"employee_recovery: installment {installment.name} ({amount}) queued against advance {advance}."
    )
    return installment.name


def monthly_employee_recovery_run() -> None:
    """Queue this month's installment for every open salary-recovery advance.

    No-op while Employee Advance recovery is disabled (the shipped default), so an
    unconfigured site never deducts a wage. One advance failing never
    stops the rest.
    """
    if not frappe.db.get_single_value("Salis Settings", "enable_employee_advance_recovery"):
        return
    if not _source_link_available():
        return

    advances = frappe.get_all(
        "Employee Advance",
        filters={
            "docstatus": 1,
            "repay_unclaimed_amount_from_salary": 1,
            "status": ["in", OPEN_ADVANCE_STATUSES],
            SOURCE_DOCTYPE_FIELD: ["is", "set"],
        },
        pluck="name",
    )
    for advance in advances:
        try:
            schedule_recovery_deduction(advance)
        except Exception:
            frappe.log_error(
                title="employee_recovery: installment failed",
                message=f"Advance {advance}\n{frappe.get_traceback()}",
            )
