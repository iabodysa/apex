"""Remove the obsolete Worker default from otherwise exact Driver token rows."""

import frappe


def execute():
    names = frappe.get_all(
        "Masar Worker Token",
        filters={
            "holder_type": "Driver",
            "driver": ["is", "set"],
            "party_type": "Employee",
            "employee": ["is", "not set"],
            "party": ["is", "not set"],
        },
        pluck="name",
    )
    for name in names:
        frappe.db.set_value(
            "Masar Worker Token",
            name,
            "party_type",
            None,
            update_modified=False,
        )
