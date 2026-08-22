# Copyright (c) 2026, afmcoltd
"""Give every building supervisor the User Permission row their access depends on.

``Building.on_update`` grants and revokes this row whenever ``responsible_supervisor``
changes, the same shape erpnext uses for Company on an Employee
(erpnext/setup/doctype/employee/employee.py:99-101). Any building saved without that hook
carries no row, and the row IS the estate: ``db_query.add_user_permissions``
(frappe/model/db_query.py:1067) builds the whole restriction from it. A supervisor missing
one is refused every estate by ``habitat.permissions.refuse_a_supervisor_with_no_building``
rather than widened to all of them, so the cost of a gap is a blank list, not a leak.

Idempotent: an existing row is left alone, so a re-run adds nothing. Skips a supervisor
with no User record, because User Permission's own link validation would refuse it.
"""

import frappe


def execute():
    """Create the missing Building User Permission for each supervised building."""
    for row in frappe.get_all(
        "Building",
        filters={"responsible_supervisor": ["is", "set"]},
        fields=["name", "responsible_supervisor"],
    ):
        if frappe.db.exists(
            "User Permission",
            {
                "user": row.responsible_supervisor,
                "allow": "Building",
                "for_value": row.name,
            },
        ):
            continue
        if not frappe.db.exists("User", row.responsible_supervisor):
            continue
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": row.responsible_supervisor,
                "allow": "Building",
                "for_value": row.name,
            }
        ).insert(ignore_permissions=True)
