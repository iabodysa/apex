from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt


RECOVERY_COMPONENT = "Employee Advance Recovery"


def seed_recovery_component():
    """Create the native HRMS deduction component in a safe disabled state."""
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
    component.insert(ignore_permissions=True)
    return component.name


def configure_recovery(*, enabled=False, company=None, salary_component=None, max_percent=None):
    """Apply setup-wizard recovery choices without bypassing native HRMS validation."""
    settings = frappe.get_single("Salis Settings")
    if not enabled:
        settings.enable_employee_advance_recovery = 0
        settings.save(ignore_permissions=True)
        return False

    if not company:
        frappe.throw(_("Company is required to enable Employee Advance recovery."))
    advance_account = frappe.db.get_value(
        "Company", company, "default_employee_advance_account"
    )
    if not advance_account:
        frappe.throw(
            _("Set the Company's Default Employee Advance Account before enabling recovery.")
        )
    if frappe.db.get_value("Account", advance_account, "account_type") != "Receivable":
        frappe.throw(_("The Default Employee Advance Account must be Receivable."))

    salary_component = salary_component or seed_recovery_component()
    if not salary_component or frappe.db.get_value(
        "Salary Component", salary_component, "type"
    ) != "Deduction":
        frappe.throw(_("Select a Salary Component of type Deduction for recovery."))
    component = frappe.get_doc("Salary Component", salary_component)
    account_row = next((row for row in component.accounts if row.company == company), None)
    if account_row:
        account_row.account = advance_account
    else:
        component.append("accounts", {"company": company, "account": advance_account})
    component.disabled = 0
    component.save(ignore_permissions=True)

    settings.enable_employee_advance_recovery = 1
    settings.employee_advance_recovery_component = salary_component
    settings.employee_advance_recovery_max_percent = flt(max_percent) or 50
    settings.save(ignore_permissions=True)
    return bool(cint(settings.enable_employee_advance_recovery))
