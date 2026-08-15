# Copyright (c) 2026, afmcoltd
"""Normalized monthly telecom commitment grouped by cost center, company-scoped."""

import frappe
from frappe import _

from apex.logistay import permissions
from apex.logistay.utils.billing import monthly_equivalent
from apex.apex_core.utils.report_summary import count_card, total_card


def execute(filters=None):
    """Lists normalized monthly telecom commitment and active contract count grouped by cost center."""
    filters = filters or {}
    columns = [
        {"label": frappe._("Cost Center"), "fieldname": "cost_center", "fieldtype": "Data", "width": 220},
        {"label": frappe._("Monthly Commitment"), "fieldname": "monthly_commitment", "fieldtype": "Currency", "width": 170},
        {"label": frappe._("Active Contracts"), "fieldname": "contract_count", "fieldtype": "Int", "width": 130},
    ]

    query = {"docstatus": 1, "status": "Active"}
    if filters.get("company"):
        query["company"] = filters["company"]

    restrict, allowed = permissions.report_company_scope(frappe.session.user, doctype="Telecom Contract")
    if restrict:
        if not allowed:
            return columns, []
        chosen = query.get("company")
        if chosen and chosen not in allowed:
            return columns, []
        if not chosen:
            query["company"] = ["in", allowed]

    rows = frappe.get_all(
        "Telecom Contract",
        filters=query,
        fields=["cost_center", "recurring_amount", "billing_frequency"],
    )
    agg = {}
    for row in rows:
        key = row.cost_center or frappe._("Unassigned")
        bucket = agg.setdefault(key, {"monthly": 0.0, "count": 0})
        bucket["monthly"] += monthly_equivalent(row.recurring_amount, row.billing_frequency)
        bucket["count"] += 1

    data = [
        {
            "cost_center": key,
            "monthly_commitment": round(bucket["monthly"], 2),
            "contract_count": bucket["count"],
        }
        for key, bucket in sorted(agg.items(), key=lambda kv: kv[1]["monthly"], reverse=True)
    ]
    summary = [
        count_card(_("Cost Centres"), data),
        total_card(_("Contracts"), data, "contract_count", "Int"),
        total_card(_("Monthly Commitment"), data, "monthly_commitment", "Currency"),
    ]
    return columns, data, None, None, summary
