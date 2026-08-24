# Copyright (c) 2026, afmcoltd

import frappe


def execute():
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
        ).insert()
