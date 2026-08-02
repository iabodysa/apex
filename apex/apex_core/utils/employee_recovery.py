# Copyright (c) 2026, AFMCO and contributors
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

This module only decides WHETHER and HOW MUCH, mirroring the Salary Deduction
Policy contract already used by Custody Damage Assessment: the deduction side is
gated by the policy (master switch + per-type rule, both OFF by default), so no
wage is ever touched until the policy is activated after legal review. Raising the
receivable is NOT policy-gated — an advance is a lawful receivable regardless; only
its recovery from wages is capped by KSA Labor Law Art. 91.

Recovery is predicated on the company having actually paid: outstanding is measured
from ``paid_amount``, which only the native payment entry sets. Nothing is deducted
from a wage for money the company never disbursed.

Source linkage is two-way and duplicate-safe: the source document keeps its own
``Employee Advance`` link, and the advance carries ``custom_source_doctype`` /
``custom_source_document`` (Customization shipped in apex_core/custom/employee_advance.json),
so "one source document maps to at most one advance" survives an amendment on
either side.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, get_first_day, get_last_day, getdate, today

from apex.apex_core.doctype.salary_deduction_policy.salary_deduction_policy import (
    KSA_MAX_TOTAL_DEDUCTION_PERCENT,
    get_policy,
)

# [#a102sf] Customization fields on the HRMS Employee Advance (see
# apex_core/custom/employee_advance.json) — the reverse link back to the operational
# document that caused the recovery.
SOURCE_DOCTYPE_FIELD = "custom_source_doctype"
SOURCE_DOCNAME_FIELD = "custom_source_document"

# [#a102os] A submitted advance still carrying a balance to recover. "Returned" and
# "Claimed" are terminal; "Cancelled" is docstatus 2.
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
    """
    logger = frappe.logger()
    amount = flt(amount)
    if not (employee and amount > 0):
        return None

    # [#a102sl] Without the source Customization there is no way to guarantee "maps
    # once", and an untraceable receivable is worse than none — so refuse rather than
    # risk raising a second advance for the same loss on the next submit.
    if not _source_link_available():
        logger.warning(
            f"employee_recovery: {source_doctype} {source_name} — the Employee Advance source "
            f"Customization has not synced yet (run bench migrate). No Employee Advance raised."
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

    # [#a102ac] HRMS requires a Receivable advance account and throws on submit
    # otherwise; check first so a misconfigured account degrades to "no recovery
    # raised" instead of blocking the operational document.
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
            # [#a102rs] Marks the advance as recovered from salary, which is what
            # enables HRMS's own return-through-Additional-Salary path.
            "repay_unclaimed_amount_from_salary": 1,
            SOURCE_DOCTYPE_FIELD: source_doctype,
            SOURCE_DOCNAME_FIELD: source_name,
        }
    )
    # audit-ok: system-raised receivable. Authority was already enforced upstream by
    # the submit permission on the source document (which also carries the worker's
    # signed consent); a fleet approver is not expected to hold HR create rights.
    advance.insert(ignore_permissions=True)  # audit-ok
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
            # [#a102rc] A recurring row only claims the period it actually spans.
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
    """The per-period installment agreed on the source document, or 0.0 for "no
    agreed installment". Read generically so any source DocType that grows an
    ``installment_amount`` field participates without touching this module."""
    if not (source_doctype and source_name):
        return 0.0
    # A retired source DocType leaves the Dynamic Link dangling; get_meta would throw.
    if not frappe.db.exists("DocType", source_doctype):
        return 0.0
    if not frappe.get_meta(source_doctype).has_field("installment_amount"):
        return 0.0
    return flt(frappe.db.get_value(source_doctype, source_name, "installment_amount"))


def bounded_installment(
    outstanding: float, statutory_cap: float, availability: float, agreed: float = 0.0
) -> float:
    """The lowest binding limit on one installment, floored at zero.

    Pure arithmetic, deliberately free of any DB read so the KSA-cap rule itself is
    provable without a payroll-configured site: ``agreed <= 0`` means "no installment
    agreed" (not "recover nothing"), and any single limit hitting zero — a cleared
    balance, a fully committed pay period — defers the whole recovery.
    """
    limits = [flt(outstanding), flt(statutory_cap), flt(availability)]
    if flt(agreed) > 0:
        limits.append(flt(agreed))
    return max(flt(min(limits), 2), 0.0)


def compute_recovery_installment(advance: str, payroll_date: str | None = None) -> float:
    """SAR recoverable from ONE pay period against ``advance``.

    The lowest of every binding limit, floored at zero:

      * outstanding — what the company actually paid out and has not recovered yet,
        minus installments already queued;
      * the agreed installment recorded on the source document (0 = none agreed);
      * the statutory cap — the lower of the type rule's and the policy's max % of
        wage, itself never above the KSA Labor Law Art. 91 50% ceiling;
      * payroll availability — the wage left after the deductions already claiming
        that period, so net pay never goes negative.

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

    policy = get_policy()
    rule = policy.get_type_rule("Damage")
    if not rule:
        return 0.0

    wage = _monthly_wage(advance_doc.employee, payroll_date)
    if wage <= 0:
        return 0.0

    # [#a102cp] Lowest of the per-type cap, the policy-wide cap and the statutory
    # ceiling — a mis-set policy can only ever narrow the deduction, never widen it.
    cap_percent = min(
        flt(rule.max_percent_of_salary),
        flt(policy.global_max_percent_of_salary) or KSA_MAX_TOTAL_DEDUCTION_PERCENT,
        KSA_MAX_TOTAL_DEDUCTION_PERCENT,
    )
    committed = _scheduled_deductions(
        advance_doc.employee, get_first_day(payroll_date), get_last_day(payroll_date)
    )
    return bounded_installment(
        outstanding=outstanding,
        statutory_cap=wage * cap_percent / 100.0,
        availability=wage - committed,
        agreed=_agreed_installment(
            advance_doc.get(SOURCE_DOCTYPE_FIELD), advance_doc.get(SOURCE_DOCNAME_FIELD)
        ),
    )


def _recovery_component(policy) -> str | None:
    """The Salary Component the Damage rule deducts through, verified to be of type
    Deduction. ``None`` (logged) when the policy has no usable component — an Earning
    component would silently PAY the worker the damage, so it must never be used.

    TYPE is checked here; the component's LEDGER ACCOUNT deliberately is not, and an
    earlier clause that claimed otherwise was wrong. This module writes no GL entry.
    It reads the advance account off ``Company.default_employee_advance_account``
    (never choosing it) and validates only what HRMS itself enforces on submit — that
    the account is Receivable. Recovery is then reconciled by HRMS off the
    ``ref_doctype``/``ref_docname`` link on the Additional Salary, not by any equality
    between the component's account and the advance account. Adding such a check here
    would fail CLOSED and SILENTLY (a ``None`` return queues no installment, ever), so
    a site whose deduction component posts to a clearing account would lose wage
    recovery that works today. Account agreement is payroll configuration, verifiable
    only against a running HRMS site — not an invariant this module can assert.
    """
    rule = policy.get_type_rule("Damage")
    if not rule:
        return None
    component = rule.salary_component or policy.default_salary_component
    if not component:
        frappe.logger().warning(
            "employee_recovery: Salary Deduction Policy > Damage rule has no Salary Component "
            "(and no default). No installment scheduled."
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
    frappe.has_permission("Employee Advance", "read", doc=advance, throw=True)
    frappe.has_permission("Additional Salary", "create", throw=True)

    payroll_date = payroll_date or today()
    period_start = get_first_day(payroll_date)
    period_end = get_last_day(payroll_date)

    # [#a102ds] Duplicate-safe: one installment per advance per pay period, counting
    # drafts, so a re-run (scheduler retry, manual click) is a no-op.
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

    policy = get_policy()
    component = _recovery_component(policy)
    if not component:
        return None

    amount = compute_recovery_installment(advance, payroll_date)
    if amount <= 0:
        frappe.logger().info(
            f"employee_recovery: nothing recoverable from advance {advance} for {payroll_date}. Deferred."
        )
        return None

    advance_doc = frappe.db.get_value(
        "Employee Advance", advance, ["employee", "company", "currency"], as_dict=True
    )
    installment = frappe.get_doc(
        {
            "doctype": "Additional Salary",
            "employee": advance_doc.employee,
            "company": advance_doc.company,
            "currency": advance_doc.currency,
            "salary_component": component,
            "amount": amount,
            "payroll_date": payroll_date,
            # [#a102ow] An installment ADDS a deduction; it must never overwrite a
            # salary-structure row (HRMS's own advance-return helper does the same).
            "overwrite_salary_structure_amount": 0,
            # [#a102rl] The source link HRMS itself keys the recovered balance on.
            "ref_doctype": "Employee Advance",
            "ref_docname": advance,
        }
    )
    # audit-ok: the caller's Additional Salary create right is checked explicitly at
    # the top of this function; the scheduler path runs as Administrator.
    installment.insert(ignore_permissions=True)  # audit-ok
    frappe.logger().info(
        f"employee_recovery: installment {installment.name} ({amount}) queued against advance {advance}."
    )
    return installment.name


def monthly_employee_recovery_run() -> None:
    """Queue this month's installment for every open salary-recovery advance.

    No-op while the Salary Deduction Policy Damage rule is disabled (the shipped
    default), so an un-reviewed site never deducts a wage. One advance failing never
    stops the rest.
    """
    if not get_policy().get_type_rule("Damage"):
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
