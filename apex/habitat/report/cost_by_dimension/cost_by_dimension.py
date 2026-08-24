# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _
from frappe.query_builder.functions import Sum, Count

from apex.apex_core.utils.report_summary import card, total_card


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    summary = [
        total_card(_("Ledger Entries"), data, "entries", "Int"),
        total_card(_("Total Cost"), data, "total_cost", "Currency"),
        card(_("Buildings"), len({r.get("building") for r in data if r.get("building")}), "Int"),
    ]
    return columns, data, None, None, summary


def get_columns():
    return [
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 200},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 200},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 200},
        {"label": _("Ledger Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 120},
        {"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 160},
    ]


def get_data(filters):
    ledger = frappe.qb.DocType("Accommodation Ledger")

    query = (
        frappe.qb.from_(ledger)
        .select(
            ledger.company,
            ledger.building,
            ledger.project,
            Count(ledger.name).as_("entries"),
            Sum(ledger.employee_daily_share).as_("total_cost"),
        )
        .where(ledger.posting_mode == "Operational Memo")
        .where(ledger.reversal_of.isnull())
        .groupby(ledger.company, ledger.building, ledger.project)
        .orderby(ledger.company)
        .orderby(ledger.building)
        .orderby(ledger.project)
    )

    if filters.get("company"):
        query = query.where(ledger.company == filters.company)
    if filters.get("building"):
        query = query.where(ledger.building == filters.building)
    if filters.get("project"):
        query = query.where(ledger.project == filters.project)
    if filters.get("from_date"):
        query = query.where(ledger.posting_date >= filters.from_date)
    if filters.get("to_date"):
        query = query.where(ledger.posting_date <= filters.to_date)

    return query.run(as_dict=True)
