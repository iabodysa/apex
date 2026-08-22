# Copyright (c) 2026, afmcoltd

"""Cost by Dimension.

Aggregates operational accommodation cost from the Accommodation Ledger
(the canonical internal cost-allocation ledger) grouped by the cost
dimensions Company, Building and Project, over a posting-date range.

Cost magnitude is the per-row ``employee_daily_share`` posted by the
``daily_accommodation_cost_allocation`` scheduler as Operational Memo
entries. Reversal rows are excluded so the totals reflect net cost.

Built with frappe.qb (parameterised) so user-supplied filters are bound,
never string-interpolated.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum, Count

from apex.apex_core.utils.report_summary import card, total_card


def execute(filters=None):
    """Returns the columns, rows and cards for cost aggregated by company, building and project."""
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
    """Returns the column definitions for the cost-by-dimension report."""
    return [
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 200},
        {"label": _("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 200},
        {"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 200},
        {"label": _("Ledger Entries"), "fieldname": "entries", "fieldtype": "Int", "width": 120},
        {"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 160},
    ]


def get_data(filters):
    """Sums non-reversal ledger cost by company, building and project, per the given filters.

    Confined to the reader's own buildings first. A Script Report builds its own SQL, so
    ``permission_query_conditions`` never runs against it — the scope has to be applied
    here or a building-scoped supervisor reads every company's costs on the site.
    """
    from apex.habitat import permissions

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Accommodation Ledger"
    )
    if restrict and not allowed:
        return []

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
    if restrict:
        query = query.where(ledger.building.isin(allowed))

    return query.run(as_dict=True)
