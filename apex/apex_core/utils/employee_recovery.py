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
from a wage for money the company never disbursed. The per-period headroom comes from
an unsaved native HRMS Salary Slip preview, so structure deductions, tax, loans and
payment-day proration remain HRMS-owned.

Source linkage is two-way and duplicate-safe: the source row is locked before the
existing-link check and insert, and the source document keeps its own
``Employee Advance`` link, and the advance carries ``custom_source_doctype`` /
``custom_source_document`` (Customization shipped in apex_core/custom/employee_advance.json),
so "one source document maps to at most one advance" survives an amendment on
either side.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate, today
from hrms.hr.doctype.employee_advance import employee_advance as native_employee_advance
from hrms.payroll.doctype.salary_structure import (
    salary_structure as native_salary_structure,
)

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT

SOURCE_DOCTYPE_FIELD = "custom_source_doctype"
SOURCE_DOCNAME_FIELD = "custom_source_document"
SIGNED_EVIDENCE_FIELD = "custom_signed_evidence"
AGREED_INSTALLMENT_FIELD = "custom_agreed_installment"

OPEN_ADVANCE_STATUSES = ("Unpaid", "Paid")


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


def backfill_recovery_snapshots():
    """Fill new immutable snapshots from linked Vehicle Incidents after customization sync."""
    meta = frappe.get_meta("Employee Advance")
    if not all(
        meta.has_field(fieldname)
        for fieldname in (SIGNED_EVIDENCE_FIELD, AGREED_INSTALLMENT_FIELD)
    ):
        return
    advances = frappe.get_all(
        "Employee Advance",
        filters={
            SOURCE_DOCTYPE_FIELD: "Vehicle Incident",
            SOURCE_DOCNAME_FIELD: ["is", "set"],
        },
        fields=[
            "name",
            SOURCE_DOCNAME_FIELD,
            SIGNED_EVIDENCE_FIELD,
            AGREED_INSTALLMENT_FIELD,
        ],
    )
    for advance in advances:
        evidence_blank = not advance.get(SIGNED_EVIDENCE_FIELD)
        installment_blank = advance.get(AGREED_INSTALLMENT_FIELD) in (None, "", 0, 0.0)
        if not (evidence_blank or installment_blank):
            continue
        source = frappe.db.get_value(
            "Vehicle Incident",
            advance.get(SOURCE_DOCNAME_FIELD),
            ["worker_signature", "installment_amount"],
            as_dict=True,
        )
        if not source:
            continue
        updates = {}
        if evidence_blank and source.get("worker_signature"):
            updates[SIGNED_EVIDENCE_FIELD] = source.worker_signature
        if installment_blank:
            updates[AGREED_INSTALLMENT_FIELD] = flt(source.get("installment_amount"))
        if updates:
            frappe.db.set_value(
                "Employee Advance",
                advance.name,
                updates,
                update_modified=False,
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

    source_fields = ["name"]
    if source_doctype == "Vehicle Incident":
        source_fields += ["worker_signature", "installment_amount"]
    source = frappe.db.get_value(
        source_doctype,
        source_name,
        source_fields,
        as_dict=True,
        for_update=True,
    )
    if not source:
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

    advance_account = frappe.db.get_value(
        "Company", company, "default_employee_advance_account"
    )
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
            SIGNED_EVIDENCE_FIELD: (
                source.get("worker_signature")
                if source_doctype == "Vehicle Incident"
                else None
            ),
            AGREED_INSTALLMENT_FIELD: (
                flt(source.get("installment_amount"))
                if source_doctype == "Vehicle Incident"
                else 0
            ),
        }
    )
    advance.insert(ignore_permissions=True)
    advance.submit()
    logger.info(
        f"employee_recovery: Employee Advance {advance.name} raised for {source_doctype} {source_name}."
    )
    return advance.name


def _salary_preview(employee: str, payroll_date: str):
    """Return an unsaved native Salary Slip preview and its active assignment."""
    assignment = frappe.db.get_value(
        "Salary Structure Assignment",
        {
            "employee": employee,
            "docstatus": 1,
            "from_date": ["<=", payroll_date],
        },
        ["salary_structure", "base"],
        order_by="from_date desc",
        as_dict=True,
    )
    if not assignment or not assignment.salary_structure:
        return None, None
    try:
        preview = native_salary_structure.make_salary_slip(
            assignment.salary_structure,
            employee=employee,
            posting_date=payroll_date,
            ignore_permissions=True,
            for_preview=0,
        )
    except Exception:
        frappe.logger().warning(
            "employee_recovery: native Salary Slip preview failed for "
            f"employee {employee} on {payroll_date}. Recovery deferred."
        )
        return None, assignment
    return preview, assignment


def _draft_deductions(
    employee: str,
    start: str,
    end: str,
    exclude_additional_salary: str | None = None,
) -> float:
    """Other draft deductions not yet visible to HRMS's native Salary Slip preview.

    Submitted Additional Salaries are already included by ``make_salary_slip``. Drafts
    are subtracted separately using HRMS's same period-end recurring-row semantics.
    """
    filters = {
        "employee": employee,
        "type": "Deduction",
        "disabled": 0,
        "docstatus": 0,
    }
    if exclude_additional_salary:
        filters["name"] = ["!=", exclude_additional_salary]
    rows = frappe.get_all(
        "Additional Salary",
        filters=filters,
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
            if getdate(row.from_date) > getdate(end) or getdate(row.to_date) < getdate(
                end
            ):
                continue
        total += flt(row.amount)
    return total


def _pending_installments(
    advance: str, exclude_additional_salary: str | None = None
) -> float:
    """Installments already queued against an advance but not yet submitted.

    A submitted installment has already moved the advance's ``return_amount``
    natively; a draft has not, so it must be subtracted from the outstanding balance
    by hand or the next run would queue the same money twice.
    """
    filters = {
        "ref_doctype": "Employee Advance",
        "ref_docname": advance,
        "docstatus": 0,
        "disabled": 0,
    }
    if exclude_additional_salary:
        filters["name"] = ["!=", exclude_additional_salary]
    queued = frappe.get_all(
        "Additional Salary",
        filters=filters,
        pluck="amount",
    )
    return sum(flt(amount) for amount in queued)


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


def compute_recovery_installment(
    advance: str,
    payroll_date: str | None = None,
    *,
    exclude_additional_salary: str | None = None,
    locked_advance=None,
) -> float:
    """SAR recoverable from ONE pay period against ``advance``.

    The lowest of every binding limit, floored at zero:

      * outstanding — what the company actually paid out and has not recovered yet,
        minus installments already queued;
      * the agreed installment snapshotted on the Employee Advance (0 = none agreed);
      * the configured scheduling limit, never above 50% of actual-period gross pay;
      * nonnegative native preview net pay less other draft deductions.

    0.0 means "recover nothing this period" (policy off, no wage known, balance
    cleared, or the period is fully committed) and the caller must defer, not post.
    """
    payroll_date = payroll_date or today()
    fields = [
        "employee",
        "paid_amount",
        "claimed_amount",
        "return_amount",
        "docstatus",
        "status",
    ]
    if _source_link_available():
        fields += [
            SOURCE_DOCTYPE_FIELD,
            SOURCE_DOCNAME_FIELD,
            AGREED_INSTALLMENT_FIELD,
        ]
    advance_doc = locked_advance or frappe.db.get_value(
        "Employee Advance", advance, fields, as_dict=True
    )
    if not advance_doc or advance_doc.docstatus != 1:
        return 0.0

    outstanding = (
        flt(advance_doc.paid_amount)
        - flt(advance_doc.get("claimed_amount"))
        - flt(advance_doc.return_amount)
        - _pending_installments(advance, exclude_additional_salary)
    )
    if outstanding <= 0:
        return 0.0

    enabled = frappe.db.get_single_value(
        "Salis Settings", "enable_employee_advance_recovery"
    )
    if not enabled:
        return 0.0

    preview, _assignment = _salary_preview(advance_doc.employee, payroll_date)
    if not preview:
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
    period_start = get_first_day(payroll_date)
    period_end = get_last_day(payroll_date)
    headroom = max(
        flt(preview.net_pay)
        - _draft_deductions(
            advance_doc.employee,
            period_start,
            period_end,
            exclude_additional_salary,
        ),
        0.0,
    )
    return bounded_installment(
        outstanding=outstanding,
        configured_limit=min(
            flt(preview.gross_pay) * cap_percent / 100.0,
            headroom,
        ),
        agreed=flt(advance_doc.get(AGREED_INSTALLMENT_FIELD)),
    )


def validate_recovery_additional_salary(doc, method=None):
    """Revalidate an Apex recovery draft immediately before native HRMS submission."""
    if doc.ref_doctype != "Employee Advance" or not doc.ref_docname:
        return
    if not _source_link_available():
        return
    source_doctype = frappe.db.get_value(
        "Employee Advance", doc.ref_docname, SOURCE_DOCTYPE_FIELD
    )
    if not source_doctype:
        return
    advance = frappe.get_doc("Employee Advance", doc.ref_docname, for_update=True)
    if not advance.get(SOURCE_DOCTYPE_FIELD):
        return
    if advance.docstatus != 1 or advance.status not in OPEN_ADVANCE_STATUSES:
        frappe.throw(_("The linked Employee Advance is no longer open for recovery."))
    allowed = compute_recovery_installment(
        advance.name,
        doc.payroll_date,
        exclude_additional_salary=doc.name,
        locked_advance=advance,
    )
    if allowed <= 0 or flt(doc.amount) > allowed:
        frappe.throw(
            _(
                "This recovery installment is stale or exceeds the current payroll headroom. "
                "Cancel it and schedule a new draft."
            )
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
