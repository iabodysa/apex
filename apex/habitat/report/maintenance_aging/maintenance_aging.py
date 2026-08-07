# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.utils import date_diff, today

from apex.habitat.permissions import report_maintenance_request_scope
from apex.apex_core.utils.report_summary import count_card, total_card


_PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
_SLA_DAYS = {"Critical": 1, "High": 3, "Medium": 7, "Low": 14}


def execute(filters=None):
    """Returns open maintenance requests with age, SLA and breach status, sorted by breach, priority."""
    filters = filters or {}

    columns = [
        {"label": frappe._("Request"), "fieldname": "name", "fieldtype": "Link", "options": "Maintenance Request", "width": 150},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 150},
        {"label": frappe._("Issue Type"), "fieldname": "issue_type", "fieldtype": "Data", "width": 130},
        {"label": frappe._("Description"), "fieldname": "description", "fieldtype": "Small Text", "width": 240},
        {"label": frappe._("Priority"), "fieldname": "priority", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Assigned To"), "fieldname": "assigned_to", "fieldtype": "Link", "options": "User", "width": 140},
        {"label": frappe._("Age (Days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 90},
        {"label": frappe._("SLA (Days)"), "fieldname": "sla_days", "fieldtype": "Int", "width": 90},
        {"label": frappe._("SLA Breached"), "fieldname": "sla_breached", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Cost of Repair"), "fieldname": "cost_of_repair", "fieldtype": "Currency", "width": 140},
    ]

    open_statuses = ["Open", "Assigned", "In Progress", "Reopened"]
    if filters.get("status"):
        query_filters = {"status": filters["status"]}
    else:
        query_filters = {"status": ["in", open_statuses]}
    if filters.get("building"):
        query_filters["building"] = filters["building"]
    if filters.get("priority"):
        query_filters["priority"] = filters["priority"]
    if filters.get("company"):
        query_filters["company"] = filters["company"]
    if filters.get("cost_center"):
        query_filters["cost_center"] = filters["cost_center"]

    restrict, scope_user = report_maintenance_request_scope()
    or_filters = (
        {"owner": scope_user, "assigned_to": scope_user} if restrict else None
    )

    rows = frappe.get_all(
        "Maintenance Request",
        filters=query_filters,
        or_filters=or_filters,
        fields=[
            "name", "building", "issue_type", "issue_description as description",
            "priority", "status", "assigned_to", "cost_of_repair", "creation",
        ],
        order_by="creation asc",
    )

    data = []
    today_str = today()
    for row in rows:
        age_days = date_diff(today_str, row.creation) if row.creation else 0
        sla = _SLA_DAYS.get(row.priority or "Low", 14)
        breached = 1 if age_days > sla else 0
        data.append({
            "name": row.name,
            "building": row.building,
            "issue_type": row.issue_type or "",
            "description": row.description or "",
            "priority": row.priority or "",
            "status": row.status,
            "assigned_to": row.assigned_to or "",
            "age_days": age_days,
            "sla_days": sla,
            "sla_breached": breached,
            "cost_of_repair": row.cost_of_repair or 0,
        })

    data.sort(key=lambda r: (-(r["sla_breached"]), _PRIORITY_ORDER.get(r["priority"], 99), -r["age_days"]))

    summary = [
        count_card(_("Open Requests"), data),
        count_card(
            _("Past SLA"),
            data,
            lambda r: (r.get("age_days") or 0) > (r.get("sla_days") or 0) > 0,
            "Red",
        ),
        total_card(_("Repair Cost"), data, "cost_of_repair", "Currency"),
    ]
    return columns, data, None, _build_chart(data), summary


def _build_chart(data):
    """Stacked bar of within-SLA vs SLA-breached open requests, by priority."""
    if not data:
        return None
    order = sorted(_PRIORITY_ORDER, key=lambda p: _PRIORITY_ORDER[p])
    within = {p: 0 for p in order}
    breached = {p: 0 for p in order}
    for row in data:
        priority = row.get("priority") if row.get("priority") in within else "Low"
        if row.get("sla_breached"):
            breached[priority] += 1
        else:
            within[priority] += 1
    return {
        "type": "bar",
        "data": {
            "labels": order,
            "datasets": [
                {"name": frappe._("Within SLA"), "values": [within[p] for p in order]},
                {"name": frappe._("SLA Breached"), "values": [breached[p] for p in order]},
            ],
        },
    }
