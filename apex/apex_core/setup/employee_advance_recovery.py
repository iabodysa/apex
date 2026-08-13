from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt


RECOVERY_COMPONENT = "Employee Advance Recovery"
MAX_RECOVERY_PERCENT = 50.0


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
    if not salary_component:
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
    settings.employee_advance_recovery_max_percent = max_percent
    settings.save(ignore_permissions=True)
    return bool(cint(settings.enable_employee_advance_recovery))
