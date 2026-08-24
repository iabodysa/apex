# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

RECOVERY_COMPONENT = "Employee Advance Recovery"
MAX_RECOVERY_PERCENT = 50.0

def seed_recovery_component():
    if not frappe.db.exists("DocType", "Salary Component"):
        return None
    existing = frappe.db.exists("Salary Component", RECOVERY_COMPONENT)
    if existing:
        return existing
    component = frappe.get_doc(
        {
            "doctype": "Salary Component",
            "salary_component": RECOVERY_COMPONENT,
            "salary_component_abbr": "EAR",
            "type": "Deduction",
            "depends_on_payment_days": 0,
            "disabled": 1,
        }
    )
    component.insert()
    return component.name

def ensure_advance_account(company: str) -> str:
    existing = frappe.db.get_value("Company", company, "default_employee_advance_account")
    if existing and frappe.db.get_value("Account", existing, "account_type") == "Receivable":
        return existing

    match = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "account_type": "Receivable",
            "is_group": 0,
            "disabled": 0,
            "account_name": ("like", "%Advance%"),
        },
        "name",
    )
    if not match:
        parent = frappe.db.get_value(
            "Account",
            {"company": company, "account_name": "Current Assets", "is_group": 1},
            "name",
        ) or frappe.db.get_value("Account", {"company": company, "is_group": 1}, "name")
        if not parent:
            frappe.throw(
                _("Company {0} has no chart of accounts yet.").format(company)
            )
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "Employee Advances (Receivable)",
                "parent_account": parent,
                "account_type": "Receivable",
                "company": company,
                "is_group": 0,
            }
        )
        account.insert()
        match = account.name

    frappe.db.set_value("Company", company, "default_employee_advance_account", match)
    return match

def configure_recovery(*, enabled=False, company=None, salary_component=None, max_percent=None):
    settings = frappe.get_single("Salis Settings")
    max_percent = (
        MAX_RECOVERY_PERCENT if max_percent in (None, "") else flt(max_percent)
    )
    if not 0 < max_percent <= MAX_RECOVERY_PERCENT:
        frappe.throw(
            _(
                "Maximum Recovery Percent must be greater than 0 and no more than {0}."
            ).format(int(MAX_RECOVERY_PERCENT))
        )
    if salary_component and frappe.db.get_value(
        "Salary Component", salary_component, "type"
    ) != "Deduction":
        frappe.throw(_("Select a Salary Component of type Deduction for recovery."))

    if not enabled:
        settings.enable_employee_advance_recovery = 0
        if salary_component:
            settings.employee_advance_recovery_component = salary_component
        settings.employee_advance_recovery_max_percent = max_percent
        settings.save()
        return False

    if not company:
        frappe.throw(_("Company is required to enable Employee Advance recovery."))
    advance_account = ensure_advance_account(company)

    salary_component = salary_component or seed_recovery_component()
    if not salary_component:
        frappe.throw(_("Select a Salary Component of type Deduction for recovery."))
    component = frappe.get_doc("Salary Component", salary_component)
    account_row = next((row for row in component.accounts if row.company == company), None)
    if account_row:
        account_row.account = advance_account
    else:
        component.append("accounts", {"company": company, "account": advance_account})
    component.disabled = 0
    component.save()

    settings.enable_employee_advance_recovery = 1
    settings.employee_advance_recovery_component = salary_component
    settings.employee_advance_recovery_max_percent = max_percent
    settings.save()
    return bool(cint(settings.enable_employee_advance_recovery))
