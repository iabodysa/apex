# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe import _

from apex.habitat import permissions
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    columns = [
        {"label": frappe._("Assessment"), "fieldname": "name", "fieldtype": "Link", "options": "Custody Damage Assessment", "width": 150},
        {"label": frappe._("Assessment Date"), "fieldname": "assessment_date", "fieldtype": "Date", "width": 120},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Custodian"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
        {"label": frappe._("Estimated Cost"), "fieldname": "total_estimated_replacement_cost", "fieldtype": "Currency", "width": 150},
        {"label": frappe._("Deduction Entry"), "fieldname": "deduction_entry", "fieldtype": "Link", "options": "Additional Salary", "width": 150},
    ]

    query_filters = {"docstatus": 1}
    if filters and filters.get("building"):
        query_filters["building"] = filters["building"]

    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        if not allowed:
            return columns, []
        chosen = query_filters.get("building")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query_filters["building"] = ["in", allowed]

    data = frappe.get_all(
        "Custody Damage Assessment",
        filters=query_filters,
        fields=[
            "name",
            "assessment_date",
            "building",
            "employee",
            "total_estimated_replacement_cost",
            "deduction_entry",
        ],
        order_by="assessment_date desc",
    )
    summary = [
        count_card(_("Assessments"), data),
        total_card(
            _("Estimated Replacement Cost"), data, "total_estimated_replacement_cost", "Currency"
        ),
    ]
    return columns, data, None, None, summary
