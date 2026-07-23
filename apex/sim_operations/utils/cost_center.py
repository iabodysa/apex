# Copyright (c) 2026, AFMCO and contributors
"""Cost-center resolution for SIM custody snapshots.

The employee payroll cost center follows the native HRMS rule (the same
precedence HRMS itself uses in ``set_payroll_cost_centers``): the Employee's own
``payroll_cost_center`` wins, else the Employee's Department ``payroll_cost_center``,
else the Company default cost center as a last resort. The project cost center is
read straight from ``Project.cost_center``. Both are resolved once, at custody
submission, and stored as immutable snapshots on the SIM Custody Assignment so a
later master edit never rewrites history.
"""

from __future__ import annotations

import frappe


def _field(doctype: str, name: str, fieldname: str):
    """get_cached_value guarded by meta, so a missing HRMS custom field (e.g. on
    a site without the payroll field installed) returns None instead of raising."""
    if not name:
        return None
    if not frappe.get_meta(doctype).has_field(fieldname):
        return None
    return frappe.get_cached_value(doctype, name, fieldname) or None


def resolve_employee_cost_center(employee: str | None, company: str | None = None):
    """Payroll cost center for an employee via the native HRMS precedence.

    Employee.payroll_cost_center -> Department.payroll_cost_center -> Company
    default cost center. Returns None when nothing resolves (the caller decides
    whether an unresolved cost center is acceptable)."""
    if not employee:
        return None
    cost_center = _field("Employee", employee, "payroll_cost_center")
    if not cost_center:
        department = _field("Employee", employee, "department")
        if department:
            cost_center = _field("Department", department, "payroll_cost_center")
    if not cost_center and company:
        cost_center = _field("Company", company, "cost_center")
    return cost_center or None


def resolve_project_cost_center(project: str | None):
    """Cost center attached to a Project (``Project.cost_center``), or None."""
    if not project:
        return None
    return _field("Project", project, "cost_center")
