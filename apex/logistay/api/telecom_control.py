# Copyright (c) 2026, afmcoltd
"""Read API behind the Telecom Control Desk Page.

Every endpoint is read-only, role-gated (``read`` permission on the underlying
DocType), and company-scoped through the same allowed-companies set the list
views use — so a scoped user's cards, charts, rows, expiry data and drawer never
include another company's SIMs. All inputs are bounded: filters are whitelisted to
known fields, the page size and expiry window are clamped, and aggregates run as
single grouped queries so the query count stays flat regardless of dataset size.
Unrelated employee fields are never exposed — only the custodian's name.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from apex.logistay import permissions
from apex.logistay.utils.billing import monthly_equivalent

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_EXPIRY_DAYS = 30
MAX_EXPIRY_DAYS = 365
TOP_N = 10

_SIM_FILTER_FIELDS = {
    "company": "company",
    "supplier": "supplier",
    "status": "status",
    "telecom_contract": "telecom_contract",
    "project": "current_project",
    "cost_center": "current_cost_center",
}

_SIM_ROW_FIELDS = [
    "name",
    "mobile_number",
    "status",
    "company",
    "supplier",
    "telecom_contract",
    "plan_name",
    "iccid",
    "current_custodian_type",
    "current_custodian_employee",
    "current_project",
    "current_cost_center",
    "current_assignment",
    "assigned_on",
]


def _clamp(value, low, high, default):
    """Clamps a value to the given integer range, falling back to a default when it is not numeric."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _sanitize_filters(raw):
    """Keep only whitelisted filter keys with truthy scalar values."""
    if isinstance(raw, str):
        raw = frappe.parse_json(raw) or {}
    if not isinstance(raw, dict):
        return {}
    clean = {}
    for key, column in _SIM_FILTER_FIELDS.items():
        value = raw.get(key)
        if value not in (None, "", []):
            clean[column] = value
    return clean


def _company_scope(doctype, user=None):
    """Return the list of allowed companies for ``doctype``, or None for an oversight user.

    ``None``  -> no company restriction (oversight role).
    ``[]``    -> a scoped user with no company permission: caller returns nothing.
    ``[...]`` -> restrict to these companies.

    ``doctype`` is REQUIRED and positional: it is the ``applicable_for`` narrowing key,
    and the endpoints below read two different DocTypes (SIM Card, Telecom Contract), so
    a default here would silently widen whichever of them it did not name.
    """
    restrict, allowed = permissions.report_company_scope(user or frappe.session.user, doctype=doctype)
    return allowed if restrict else None


def _apply_scope(filters, allowed):
    """Fold the company scope into a filters dict. Returns (filters, has_access)."""
    if allowed is None:
        return filters, True
    if not allowed:
        return filters, False
    chosen = filters.get("company")
    if chosen:
        if chosen not in allowed:
            return filters, False
    else:
        filters["company"] = ["in", allowed]
    return filters, True


def _grouped_counts(filters, group_field, limit=None):
    """Returns SIM Card counts grouped by one field as label and value rows, unassigned labeled."""
    rows = frappe.get_all(
        "SIM Card",
        filters=filters,
        fields=[f"{group_field} as label", "count(name) as value"],
        group_by=group_field,
        order_by="value desc",
        limit=limit,
    )
    return [{"label": r.label or _("Unassigned"), "value": r.value} for r in rows]


@frappe.whitelist()
def get_summary_cards(filters=None):
    """Returns SIM and active-contract summary counts and monthly commitment for the control desk."""
    frappe.has_permission("SIM Card", "read", throw=True)
    allowed = _company_scope("SIM Card")
    sim_filters, access = _apply_scope(_sanitize_filters(filters), allowed)
    empty = {
        "total_sims": 0,
        "assigned": 0,
        "available": 0,
        "suspended_lost": 0,
        "active_contracts": 0,
        "expiring_soon": 0,
        "monthly_commitment": 0,
    }
    if not access:
        return empty

    by_status = {r["label"]: r["value"] for r in _grouped_counts(dict(sim_filters), "status")}
    total = sum(by_status.values())

    contract_filters = {"docstatus": 1, "status": "Active"}
    if sim_filters.get("company"):
        contract_filters["company"] = sim_filters["company"]
    contracts = frappe.get_all(
        "Telecom Contract",
        filters=contract_filters,
        fields=["recurring_amount", "billing_frequency", "contract_end_date"],
    )
    horizon = add_days(today(), DEFAULT_EXPIRY_DAYS)
    commitment = 0.0
    expiring = 0
    for c in contracts:
        commitment += monthly_equivalent(c.recurring_amount, c.billing_frequency)
        if c.contract_end_date and getdate(today()) <= getdate(c.contract_end_date) <= getdate(horizon):
            expiring += 1

    return {
        "total_sims": total,
        "assigned": by_status.get("Assigned", 0),
        "available": by_status.get("Available", 0),
        "suspended_lost": by_status.get("Suspended", 0) + by_status.get("Lost", 0),
        "active_contracts": len(contracts),
        "expiring_soon": expiring,
        "monthly_commitment": round(commitment, 2),
    }


@frappe.whitelist()
def get_charts(filters=None):
    """Returns SIM Card counts grouped by status, supplier, project, and cost center for the charts."""
    frappe.has_permission("SIM Card", "read", throw=True)
    allowed = _company_scope("SIM Card")
    sim_filters, access = _apply_scope(_sanitize_filters(filters), allowed)
    if not access:
        return {"by_status": [], "by_supplier": [], "by_project": [], "by_cost_center": []}
    return {
        "by_status": _grouped_counts(dict(sim_filters), "status"),
        "by_supplier": _grouped_counts(dict(sim_filters), "supplier", limit=TOP_N),
        "by_project": _grouped_counts(dict(sim_filters), "current_project", limit=TOP_N),
        "by_cost_center": _grouped_counts(dict(sim_filters), "current_cost_center", limit=TOP_N),
    }


@frappe.whitelist()
def get_sim_rows(filters=None, page=1, page_size=DEFAULT_PAGE_SIZE):
    """Returns a paged, filtered, company-scoped list of SIM Cards with custodian names attached."""
    frappe.has_permission("SIM Card", "read", throw=True)
    allowed = _company_scope("SIM Card")
    sim_filters, access = _apply_scope(_sanitize_filters(filters), allowed)
    page = _clamp(page, 1, 100000, 1)
    page_size = _clamp(page_size, 1, MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE)
    if not access:
        return {"rows": [], "total": 0, "page": page, "page_size": page_size}

    total = frappe.db.count("SIM Card", sim_filters)
    rows = frappe.get_all(
        "SIM Card",
        filters=sim_filters,
        fields=_SIM_ROW_FIELDS,
        order_by="modified desc",
        limit_start=(page - 1) * page_size,
        limit_page_length=page_size,
    )
    _attach_custodian_names(rows)
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def _attach_custodian_names(rows):
    """Resolve custodian employee names in ONE query — only the display name, no
    other employee fields."""
    employee_ids = {r.current_custodian_employee for r in rows if r.get("current_custodian_employee")}
    names = {}
    if employee_ids:
        names = {
            e.name: e.employee_name
            for e in frappe.get_all(
                "Employee",
                filters={"name": ["in", list(employee_ids)]},
                fields=["name", "employee_name"],
            )
        }
    for r in rows:
        r["custodian_name"] = names.get(r.get("current_custodian_employee"))


@frappe.whitelist()
def get_contract_expiry(filters=None, within_days=DEFAULT_EXPIRY_DAYS):
    """Returns active or expired Telecom Contracts ending within the given day window."""
    frappe.has_permission("Telecom Contract", "read", throw=True)
    allowed = _company_scope("Telecom Contract")
    within_days = _clamp(within_days, 1, MAX_EXPIRY_DAYS, DEFAULT_EXPIRY_DAYS)
    sim_filters = _sanitize_filters(filters)
    contract_filters = {
        "docstatus": 1,
        "contract_end_date": ["<=", add_days(today(), within_days)],
        "status": ["in", ["Active", "Expired"]],
    }
    if allowed is not None:
        if not allowed:
            return {"rows": [], "within_days": within_days}
        contract_filters["company"] = ["in", allowed]
    if sim_filters.get("company"):
        chosen = sim_filters["company"]
        if allowed is not None and chosen not in allowed:
            return {"rows": [], "within_days": within_days}
        contract_filters["company"] = chosen
    if sim_filters.get("supplier"):
        contract_filters["supplier"] = sim_filters["supplier"]

    rows = frappe.get_all(
        "Telecom Contract",
        filters=contract_filters,
        fields=[
            "name",
            "supplier",
            "company",
            "contract_end_date",
            "status",
            "recurring_amount",
            "currency",
            "sim_count",
        ],
        order_by="contract_end_date asc",
        limit_page_length=MAX_PAGE_SIZE,
    )
    return {"rows": rows, "within_days": within_days}


@frappe.whitelist()
def get_cost_center_totals(filters=None):
    """Normalized monthly commitment per cost center across active contracts."""
    frappe.has_permission("Telecom Contract", "read", throw=True)
    allowed = _company_scope("Telecom Contract")
    sim_filters = _sanitize_filters(filters)
    contract_filters = {"docstatus": 1, "status": "Active"}
    if allowed is not None:
        if not allowed:
            return {"rows": []}
        contract_filters["company"] = ["in", allowed]
    if sim_filters.get("company"):
        chosen = sim_filters["company"]
        if allowed is not None and chosen not in allowed:
            return {"rows": []}
        contract_filters["company"] = chosen

    totals = {}
    for c in frappe.get_all(
        "Telecom Contract",
        filters=contract_filters,
        fields=["cost_center", "recurring_amount", "billing_frequency"],
        limit_page_length=0,
    ):
        key = c.cost_center or _("Unassigned")
        totals[key] = totals.get(key, 0.0) + monthly_equivalent(c.recurring_amount, c.billing_frequency)
    rows = [
        {"label": key, "value": round(value, 2)}
        for key, value in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {"rows": rows[:TOP_N]}


@frappe.whitelist()
def get_sim_detail(sim_card):
    """Drawer data for one SIM: its own fields plus custody history. Company and
    document permission are enforced by loading the doc through the permission
    layer; unrelated employee fields are never returned.

    """
    if not sim_card or not frappe.db.exists("SIM Card", {"name": sim_card}):
        frappe.throw(_("SIM Card {0} does not exist.").format(sim_card))
    doc = frappe.get_doc("SIM Card", sim_card)
    doc.check_permission("read")

    detail = {field: doc.get(field) for field in _SIM_ROW_FIELDS}
    detail["notes"] = doc.notes
    if doc.current_custodian_employee:
        detail["custodian_name"] = frappe.db.get_value(
            "Employee", doc.current_custodian_employee, "employee_name"
        )

    history = frappe.get_all(
        "SIM Custody Assignment",
        filters={"sim_card": sim_card, "docstatus": 1},
        fields=[
            "name",
            "action",
            "assignment_date",
            "custodian_type",
            "employee",
            "project",
            "cost_center",
        ],
        order_by="assignment_date desc, creation desc",
        limit_page_length=50,
    )
    _attach_history_names(history)
    detail["history"] = history
    return detail


def _attach_history_names(history):
    """Resolves and attaches each custody history row's employee display name in one query."""
    employee_ids = {r.employee for r in history if r.get("employee")}
    names = {}
    if employee_ids:
        names = {
            e.name: e.employee_name
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(employee_ids)]}, fields=["name", "employee_name"]
            )
        }
    for r in history:
        r["employee_name"] = names.get(r.get("employee"))
