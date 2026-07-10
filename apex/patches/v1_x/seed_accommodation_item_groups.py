# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.utils.nestedset import rebuild_tree

# [#sbmk59]
ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

ROOT = "All Item Groups"


def execute():
    # [#8z6azc]
    if not frappe.db.exists("Item Group", ROOT):
        return
    lft = frappe.db.get_value("Item Group", ROOT, "lft")
    if lft is None:
        rebuild_tree("Item Group", "parent_item_group")

    for group in ACCOMMODATION_ITEM_GROUPS:
        if frappe.db.exists("Item Group", group):
            continue
        # [#rgdpg0]
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": group,
                "parent_item_group": ROOT,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)  # audit-ok

    frappe.db.commit()
