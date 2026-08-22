# Copyright (c) 2026, afmcoltd
"""Give every building supervisor the User Permission row his access is about to depend on.

``Building.on_update`` grants and revokes this row whenever ``responsible_supervisor``
changes, the same shape erpnext uses for Company on an Employee
(erpnext/setup/doctype/employee/employee.py:99-101). A building saved before that hook
existed never got one, and until now nothing noticed: the app derived the same restriction
itself in Python. Once that derivation is removed the row IS the access, so a missing one
would silently widen a supervisor to every estate.

Idempotent: an existing row is left alone, so a re-run adds nothing.
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
