# Copyright (c) 2026, afmcoltd
"""Leave one Portal Push Subscription per endpoint on a site that could never refuse a second.

`endpoint`'s Small Text fieldtype maps to a MySQL `text` column, and Frappe's schema builder skips a
unique index on text (frappe/database/schema.py:212) even where one is declared. So a duplicate
endpoint never reached a database refusal, and a browser re-registering its push endpoint added a
row instead of replacing one — every notification then arriving twice. The controller now refuses a
duplicate; this clears the ones that landed before it did.

The newest row wins: a re-registration carries the current keys, and the row it duplicated holds
keys the browser has already replaced.
"""

import frappe


def execute():
    """Delete every duplicate but the newest, keyed on the endpoint they share.

    The delete passes ``ignore_permissions`` because a patch runs during migrate as
    Administrator with no session user whose roles could be consulted. Without the flag the
    delete is refused and the duplicates survive the migration that exists to clear them.
    """
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
