# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    duplicated = frappe.db.sql(
        """
        select endpoint
        from `tabPortal Push Subscription`
        where endpoint is not null and endpoint != ''
        group by endpoint
        having count(*) > 1
        """,
        pluck=True,
    )
    for endpoint in duplicated:
        rows = frappe.get_all(
            "Portal Push Subscription",
            filters={"endpoint": endpoint},
            fields=["name"],
            order_by="modified desc",
        )
        for stale in rows[1:]:
            frappe.delete_doc(
                "Portal Push Subscription", stale.name, force=True, ignore_permissions=True
            )
