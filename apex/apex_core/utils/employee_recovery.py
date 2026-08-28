# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
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


def find_recovery_advance(source_doctype: str, source_name: str) -> str | None:
    if not (
        source_name
        and frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD)
    ):
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
    logger = frappe.logger()
    amount = flt(amount)
    if not (employee and amount > 0):
        return None

    if not frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD):
        frappe.log_error(
            title="employee_recovery: Employee Advance source Customization not synced"[:140],
            message=(
                f"{source_doctype} {source_name} — the Employee Advance source Customization "
                "has not synced yet (run bench migrate). No Employee Advance raised."
            ),
            reference_doctype=source_doctype,
            reference_name=source_name,
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
        frappe.log_error(
            title="employee_recovery: source document does not exist"[:140],
            message=f"{source_doctype} {source_name} does not exist. No Employee Advance raised.",
            reference_doctype=source_doctype,
            reference_name=source_name,
        )
        return None

    existing = find_recovery_advance(source_doctype, source_name)
    if existing:
        return existing

    company = company or frappe.db.get_value("Employee", employee, "company")
    if not company:
        frappe.log_error(
            title="employee_recovery: employee has no company"[:140],
            message=(
                f"{source_doctype} {source_name} — employee {employee} has no company. "
                "No Employee Advance raised."
            ),
            reference_doctype=source_doctype,
            reference_name=source_name,
        )
        return None

    advance_account = frappe.db.get_value(
        "Company", company, "default_employee_advance_account"
    )
    if not advance_account:
        frappe.log_error(
            title="employee_recovery: company has no Default Employee Advance Account"[:140],
            message=(
                f"{source_doctype} {source_name} — company {company} has no Default Employee "
                "Advance Account. No Employee Advance raised."
            ),
            reference_doctype=source_doctype,
            reference_name=source_name,
        )
        return None

    if frappe.db.get_value("Account", advance_account, "account_type") != "Receivable":
        frappe.log_error(
            title="employee_recovery: advance account is not of type Receivable"[:140],
            message=(
                f"{source_doctype} {source_name} — advance account {advance_account} is not "
                "of type Receivable. No Employee Advance raised."
            ),
            reference_doctype=source_doctype,
            reference_name=source_name,
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
        frappe.log_error(
            title=f"employee_recovery: Salary Slip preview failed for {employee}"[:140],
            message=frappe.get_traceback(),
        )
        return None, assignment
    return preview, assignment


def _salary_period(preview) -> tuple[date, date] | None:
    start = getattr(preview, "start_date", None)
    end = getattr(preview, "end_date", None)
    if not (start and end):
        return None
    try:
        start = getdate(start)
        end = getdate(end)
    except (TypeError, ValueError):
        return None
    if not (start and end) or start > end:
        return None
    return start, end


def _draft_deductions(
    employee: str,
    start: str,
    end: str,
    exclude_additional_salary: str | None = None,
) -> float:
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
    salary_preview=None,
) -> float:
    payroll_date = payroll_date or today()
    fields = [
        "employee",
        "paid_amount",
        "claimed_amount",
        "return_amount",
        "docstatus",
        "status",
    ]
    if frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD):
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

    preview = salary_preview
    if preview is None:
        preview, _assignment = _salary_preview(advance_doc.employee, payroll_date)
    if not preview:
        return 0.0
    period = _salary_period(preview)
    if not period:
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
    period_start, period_end = period
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
    if doc.ref_doctype != "Employee Advance" or not doc.ref_docname:
        return
    if not frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD):
        return
    advance = frappe.get_doc("Employee Advance", doc.ref_docname, for_update=True)
    if not advance.get(SOURCE_DOCTYPE_FIELD):
        return
    if advance.docstatus != 1 or advance.status not in OPEN_ADVANCE_STATUSES:
        frappe.throw(_("The linked Employee Advance is no longer open for recovery."))
    _refuse_while_recovery_is_disabled()
    component = _recovery_component()
    advance_employee = advance.get("employee")
    advance_company = advance.get("company")
    advance_currency = advance.get("currency")
    if not (
        advance_employee
        and getattr(doc, "employee", None) == advance_employee
        and advance_company
        and getattr(doc, "company", None) == advance_company
        and advance_currency
        and getattr(doc, "currency", None) == advance_currency
        and component
        and getattr(doc, "salary_component", None) == component
        and getattr(doc, "type", None) == "Deduction"
        and getattr(doc, "is_recurring", None) == 0
        and getattr(doc, "overwrite_salary_structure_amount", None) == 0
        and getattr(doc, "payroll_date", None)
    ):
        frappe.throw(
            _(
                "This recovery Additional Salary no longer matches its Employee Advance "
                "or the configured one-period deduction. Cancel it and schedule a new draft."
            )
        )
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


def _refuse_while_recovery_is_disabled():
    if not bool(
        frappe.db.get_single_value("Salis Settings", "enable_employee_advance_recovery")
    ):
        frappe.throw(
            _(
                "Salary recovery is switched off. Turn on Employee Advance recovery in "
                "Salis Settings, and set its deduction Salary Component, before deducting "
                "from a worker's wage."
            ),
            title=_("Recovery is disabled"),
        )


def _recovery_component() -> str | None:
    if not bool(
        frappe.db.get_single_value("Salis Settings", "enable_employee_advance_recovery")
    ):
        return None
    component = frappe.db.get_single_value(
        "Salis Settings", "employee_advance_recovery_component"
    )
    if not component:
        frappe.log_error(
            title="employee_recovery: Recovery Salary Component not configured",
            message="Salis Settings has no Recovery Salary Component. No installment scheduled.",
        )
        return None
    if frappe.db.get_value("Salary Component", component, "type") != "Deduction":
        frappe.log_error(
            title="employee_recovery: Recovery Salary Component is not a Deduction",
            message=f"Salary Component {component} is not of type Deduction. No installment scheduled.",
        )
        return None
    return component


@frappe.whitelist(methods=["POST"])
def schedule_recovery_deduction(advance: str, payroll_date: str | None = None) -> str | None:
    _refuse_while_recovery_is_disabled()
    advance_doc = frappe.get_doc("Employee Advance", advance, for_update=True)
    frappe.has_permission("Employee Advance", "read", doc=advance_doc, throw=True)
    frappe.has_permission("Additional Salary", "create", throw=True)

    payroll_date = payroll_date or today()
    preview, _assignment = _salary_preview(advance_doc.employee, payroll_date)
    period = _salary_period(preview)
    if not period:
        advance_doc.add_comment(
            "Comment",
            _(
                "Salary recovery deferred for {0}: no valid Salary Slip preview period "
                "for {1}."
            ).format(payroll_date, advance_doc.employee),
        )
        return None
    period_start, period_end = period

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

    amount = compute_recovery_installment(
        advance,
        payroll_date,
        locked_advance=advance_doc,
        salary_preview=preview,
    )
    if amount <= 0:
        advance_doc.add_comment(
            "Comment",
            _("Salary recovery deferred for {0}: nothing recoverable this period.").format(
                payroll_date
            ),
        )
        return None

    installment = native_employee_advance.create_return_through_additional_salary(
        advance_doc
    )
    installment.salary_component = component
    installment.amount = amount
    installment.payroll_date = payroll_date
    installment.overwrite_salary_structure_amount = 0
    frappe.has_permission(installment.doctype, "create", throw=True)
    installment.insert()
    return installment.name


def monthly_employee_recovery_run() -> None:
    if not frappe.db.get_single_value("Salis Settings", "enable_employee_advance_recovery"):
        return
    if not frappe.get_meta("Employee Advance").has_field(SOURCE_DOCTYPE_FIELD):
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
