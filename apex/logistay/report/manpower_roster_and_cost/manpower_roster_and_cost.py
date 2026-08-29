# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, today

from apex.apex_core.utils.report_summary import card, count_card, total_card
from apex.habitat import permissions

FREELANCER = "Freelancer"
TEMPORARY_WORKER = "Temporary Worker"


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data, None, None, get_report_summary(data)


def get_columns():
    return [
        {"label": _("Type"), "fieldname": "worker_type", "fieldtype": "Data", "width": 140},
        {"label": _("Worker"), "fieldname": "worker", "fieldtype": "Dynamic Link", "options": "worker_type", "width": 160},
        {"label": _("Name"), "fieldname": "worker_name", "fieldtype": "Data", "width": 190},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Labour Supplier"), "fieldname": "labour_supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
        {"label": _("Monthly Cost"), "fieldname": "monthly_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Ends"), "fieldname": "ends_on", "fieldtype": "Date", "width": 110},
        {"label": _("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 130},
    ]


def get_data(filters):
    wanted = filters.get("worker_type")
    horizon = cint(filters.get("within_days"))
    cutoff = add_days(today(), horizon) if horizon else None

    data = []
    if wanted in (None, "", FREELANCER):
        data += freelancer_rows(filters, cutoff)
    if wanted in (None, "", TEMPORARY_WORKER):
        data += temporary_worker_rows(filters, cutoff)

    today_str = today()
    for row in data:
        row["days_to_expiry"] = (
            date_diff(row["ends_on"], today_str) if row["ends_on"] else None
        )

    data.sort(key=lambda row: (row["days_to_expiry"] is None, row["days_to_expiry"] or 0))
    return data


def freelancer_rows(filters, cutoff):
    if not frappe.has_permission(FREELANCER, "read"):
        return []

    query_filters = {}
    if filters.get("status"):
        query_filters["status"] = filters["status"]
    if filters.get("project"):
        query_filters["project"] = filters["project"]
    if cutoff:
        query_filters["contract_end_date"] = ["<=", cutoff]

    return [
        {
            "worker_type": FREELANCER,
            "worker": row.name,
            "worker_name": row.full_name or "",
            "project": row.project or "",
            "status": row.status or "",
            "labour_supplier": "",
            "monthly_cost": flt(row.monthly_salary, 2),
            "ends_on": row.contract_end_date,
        }
        for row in frappe.get_all(
            FREELANCER,
            filters=query_filters,
            fields=["name", "full_name", "project", "status", "monthly_salary", "contract_end_date"],
        )
    ]


def temporary_worker_rows(filters, cutoff):
    if not frappe.has_permission(TEMPORARY_WORKER, "read"):
        return []

    query_filters = {}
    if filters.get("status"):
        query_filters["status"] = filters["status"]
    if filters.get("project"):
        query_filters["project"] = filters["project"]
    if cutoff:
        query_filters["expiry_date"] = ["<=", cutoff]

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype=TEMPORARY_WORKER
    )
    if restrict:
        if not allowed:
            return []
        query_filters["building"] = ["in", allowed]

    return [
        {
            "worker_type": TEMPORARY_WORKER,
            "worker": row.name,
            "worker_name": row.worker_name or "",
            "project": row.project or "",
            "status": row.status or "",
            "labour_supplier": row.labour_supplier or "",
            "monthly_cost": 0.0,
            "ends_on": row.expiry_date,
        }
        for row in frappe.get_all(
            TEMPORARY_WORKER,
            filters=query_filters,
            fields=["name", "worker_name", "project", "status", "labour_supplier", "expiry_date"],
        )
    ]


def get_report_summary(data):
    lapsing = [
        row for row in data
        if row.get("days_to_expiry") is not None and row["days_to_expiry"] <= 30
    ]
    return [
        count_card(_("Workers"), data),
        count_card(_("Freelancers"), data, lambda row: row.get("worker_type") == FREELANCER),
        count_card(
            _("Temporary Workers"), data, lambda row: row.get("worker_type") == TEMPORARY_WORKER
        ),
        total_card(_("Monthly Commitment"), data, "monthly_cost", "Currency"),
        card(_("Lapsing in 30 Days"), len(lapsing), "Int", "Orange" if lapsing else None),
    ]
