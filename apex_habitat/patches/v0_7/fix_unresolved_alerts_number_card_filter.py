"""Fix Unresolved Alerts Number Card filter format.

Frappe Number Cards expect filters_json in the list format used by
frappe.get_list. The previous object-shaped filter was interpreted as a filter
on a non-existent field named `fieldname`.
"""

import frappe


def execute():
    if not frappe.db.exists("Number Card", "Unresolved Alerts"):
        return

    frappe.db.set_value(
        "Number Card",
        "Unresolved Alerts",
        "filters_json",
        '[["Habitat Operations Alert", "is_resolved", "=", 0]]',
        update_modified=False,
    )
    frappe.db.commit()
