# Copyright (c) 2026, afmcoltd

import frappe

from apex.apex_core.utils.report_summary import count_card, total_card
from apex.habitat import permissions


HEALTHY = "healthy"
FULLY_DEPRECIATED = "fully_depreciated"
OVER_BUDGET = "over_budget"
DATA_ERROR = "data_error"


def status_label(state):
    """The display text for a state, translated per request.

    Written as literals inside ``frappe._()`` rather than a table of bare strings: the
    translation scanner reads the source, so a string reached only through a variable is
    invisible to it and its Arabic row goes stale and is pruned.
    """
    if state == HEALTHY:
        return frappe._("Healthy")
    if state == FULLY_DEPRECIATED:
        return frappe._("Fully Depreciated")
    if state == OVER_BUDGET:
        return frappe._("Over Budget")
    return frappe._("Data Error")


def depreciation_pct(original_cost, book_value):
    """How much of an article's cost has been written off, capped at 100 percent.

    Pure arithmetic, so the rule can be exercised without a bench.
    """
    if not original_cost:
        return 0.0
    return min((original_cost - book_value) / original_cost * 100, 100.0)


def health_state(original_cost, book_value):
    """The article's depreciation state as a STABLE key, never as display text.

    Counting rows by comparing against the translated label instead would make the
    count depend on the language the row was built in. The key is the fact; the
    label is a rendering of it.
    """
    if not original_cost and book_value:
        return DATA_ERROR
    if book_value > 0:
        return HEALTHY
    if book_value == 0:
        return FULLY_DEPRECIATED
    return OVER_BUDGET


def get_columns():
    """The register's column set.

    A function, not a module constant: every label goes through ``frappe._()``, and a
    constant would freeze them in whatever language first imported this module.
    """
    return [
        {
            "label": frappe._("Snapshot"),
            "fieldname": "snapshot_name",
            "fieldtype": "Link",
            "options": "Operational Depreciation Snapshot",
            "width": 180,
        },
        {
            "label": frappe._("Snapshot Date"),
            "fieldname": "snapshot_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": frappe._("Building"),
            "fieldname": "building",
            "fieldtype": "Link",
            "options": "Building",
            "width": 160,
        },
        {
            "label": frappe._("Asset / Article"),
            "fieldname": "article",
            "fieldtype": "Link",
            "options": "Custody Article",
            "width": 160,
        },
        {
            "label": frappe._("Category"),
            "fieldname": "category",
            "fieldtype": "Link",
            "options": "Custody Asset Category",
            "width": 140,
        },
        {
            "label": frappe._("Original Cost"),
            "fieldname": "original_cost",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": frappe._("Book Value"),
            "fieldname": "book_value",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "label": frappe._("Age (Years)"),
            "fieldname": "age_years",
            "fieldtype": "Float",
            "precision": 2,
            "width": 100,
        },
        {
            "label": frappe._("Depreciation %"),
            "fieldname": "depreciation_pct",
            "fieldtype": "Float",
            "precision": 2,
            "width": 120,
        },
        {
            "label": frappe._("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 130,
        },
    ]


def execute(filters=None):
    """Returns the columns, rows and summary cards for the operational depreciation aging register."""
    columns = get_columns()

    parent_filters = {"docstatus": 1}
    if filters:
        if filters.get("from_date"):
            parent_filters["snapshot_date"] = [">=", filters["from_date"]]
        if filters.get("to_date"):
            if filters.get("from_date"):
                parent_filters["snapshot_date"] = [
                    "between",
                    [filters["from_date"], filters["to_date"]],
                ]
            else:
                parent_filters["snapshot_date"] = ["<=", filters["to_date"]]
        if filters.get("building"):
            parent_filters["building"] = filters["building"]

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Operational Depreciation Snapshot")
    if restrict:
        chosen = parent_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return columns, []
        if not chosen:
            parent_filters["building"] = ["in", allowed]

    snapshots = frappe.get_all(
        "Operational Depreciation Snapshot",
        filters=parent_filters,
        fields=["name", "snapshot_date", "building"],
        order_by="snapshot_date desc",
    )

    if not snapshots:
        return columns, [], None, None, get_report_summary([])

    snapshot_names = [s["name"] for s in snapshots]

    snapshot_map = {s["name"]: s for s in snapshots}

    child_rows = frappe.get_all(
        "Depreciation Snapshot Item",
        filters={"parent": ["in", snapshot_names], "parenttype": "Operational Depreciation Snapshot"},
        fields=["parent", "article", "original_cost", "book_value", "age_years"],
        order_by="parent desc",
    )

    if not child_rows:
        return columns, [], None, None, get_report_summary([])

    unique_articles = list({row["article"] for row in child_rows if row.get("article")})
    article_category_map = {}
    if unique_articles:
        articles = frappe.get_all(
            "Custody Article",
            filters={"name": ["in", unique_articles]},
            fields=["name", "category"],
        )
        article_category_map = {a["name"]: a.get("category") for a in articles}

    data = []
    for row in child_rows:
        parent = snapshot_map.get(row["parent"], {})
        original_cost = row.get("original_cost") or 0
        book_value = row.get("book_value") or 0

        state = health_state(original_cost, book_value)

        data.append(
            {
                "snapshot_name": row["parent"],
                "snapshot_date": parent.get("snapshot_date"),
                "building": parent.get("building"),
                "article": row.get("article"),
                "category": article_category_map.get(row.get("article")),
                "original_cost": original_cost,
                "book_value": book_value,
                "age_years": row.get("age_years") or 0,
                "depreciation_pct": round(depreciation_pct(original_cost, book_value), 2),
                "state": state,
                "status": status_label(state),
            }
        )

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    """Returns summary cards for asset count, original cost, book value, and fully-depreciated count."""
    return [
        count_card(frappe._("Assets"), data),
        total_card(frappe._("Original Cost"), data, "original_cost", "Currency"),
        total_card(frappe._("Book Value"), data, "book_value", "Currency"),
        count_card(
            frappe._("Fully Depreciated"),
            data,
            lambda r: r.get("state") == FULLY_DEPRECIATED,
            "Orange",
        ),
    ]
