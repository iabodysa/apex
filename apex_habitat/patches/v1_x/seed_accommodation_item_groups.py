# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.utils.nestedset import rebuild_tree

# Worker-housing procurement Item Groups. Seeded via a NestedSet-safe patch (not
# fixtures): Item Group is a NestedSet, and a fixture import on a FRESH site crashes
# when "All Item Groups" still has NULL lft/rgt (update_add_node unpacks None).
ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

ROOT = "All Item Groups"


def execute():
    # Repair the tree root first: on a fresh site its lft/rgt can be NULL, which
    # makes the controller's update_add_node unpack None and abort the insert.
    if not frappe.db.exists("Item Group", ROOT):
        return
    lft = frappe.db.get_value("Item Group", ROOT, "lft")
    if lft is None:
        rebuild_tree("Item Group", "parent_item_group")

    for group in ACCOMMODATION_ITEM_GROUPS:
        if frappe.db.exists("Item Group", group):
            continue
        # Insert through the controller so it maintains lft/rgt safely.
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": group,
                "parent_item_group": ROOT,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)  # audit-ok

    frappe.db.commit()
