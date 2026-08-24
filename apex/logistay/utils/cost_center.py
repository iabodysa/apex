# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


def _field(doctype: str, name: str, fieldname: str):
    if not name:
        return None
    if not frappe.get_meta(doctype).has_field(fieldname):
        return None
    return frappe.get_cached_value(doctype, name, fieldname) or None


def resolve_employee_cost_center(employee: str | None, company: str | None = None):
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
    if not project:
        return None
    return _field("Project", project, "cost_center")
