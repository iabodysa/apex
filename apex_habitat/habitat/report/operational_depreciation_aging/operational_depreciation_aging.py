# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
            "label": frappe._("Snapshot"),
            "fieldname": "snapshot_name",
            "fieldtype": "Link",
            "options": "Non-Financial Depreciation Snapshot",
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
            "options": "Accommodation Building",
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
            "label": frappe._("Original Cost (SAR)"),
            "fieldname": "original_cost_sar",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": frappe._("Book Value (SAR)"),
            "fieldname": "book_value_sar",
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

    # Build parent-level filters
    parent_filters = {"docstatus": 1}
    if filters:
        if filters.get("from_date"):
            parent_filters["snapshot_date"] = [">=", filters["from_date"]]
        if filters.get("to_date"):
            # Apply both bounds if both present
            if filters.get("from_date"):
                parent_filters["snapshot_date"] = [
                    "between",
                    [filters["from_date"], filters["to_date"]],
                ]
            else:
                parent_filters["snapshot_date"] = ["<=", filters["to_date"]]
        if filters.get("building"):
            parent_filters["building"] = filters["building"]

    # Fetch submitted parent snapshots
    snapshots = frappe.get_all(
        "Non-Financial Depreciation Snapshot",
        filters=parent_filters,
        fields=["name", "snapshot_date", "building"],
        order_by="snapshot_date desc",
    )

    if not snapshots:
        return columns, []

    snapshot_names = [s["name"] for s in snapshots]

    # Index snapshots by name for quick lookup
    snapshot_map = {s["name"]: s for s in snapshots}

    # Fetch all child rows for the matched snapshots
    child_rows = frappe.get_all(
        "Depreciation Snapshot Item",
        filters={"parent": ["in", snapshot_names], "parenttype": "Non-Financial Depreciation Snapshot"},
        fields=["parent", "article", "original_cost_sar", "book_value_sar", "age_years"],
        order_by="parent desc",
    )

    if not child_rows:
        return columns, []

    # Collect unique articles to resolve categories in one query
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
        original_cost = row.get("original_cost_sar") or 0
        book_value = row.get("book_value_sar") or 0

        # Depreciation percentage
        if original_cost:
            depreciation_pct = (original_cost - book_value) / original_cost * 100
        else:
            depreciation_pct = 0.0

        # Status classification
        if book_value > 0:
            status = "Healthy"
        elif book_value == 0:
            status = "Fully Depreciated"
        else:
            status = "Over Budget"

        data.append(
            {
                "snapshot_name": row["parent"],
                "snapshot_date": parent.get("snapshot_date"),
                "building": parent.get("building"),
                "article": row.get("article"),
                "category": article_category_map.get(row.get("article")),
                "original_cost_sar": original_cost,
                "book_value_sar": book_value,
                "age_years": row.get("age_years") or 0,
                "depreciation_pct": round(depreciation_pct, 2),
                "status": status,
            }
        )

    return columns, data
