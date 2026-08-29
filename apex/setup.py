# Copyright (c) 2026, afmcoltd
import json

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSetMultipleRootsError, rebuild_tree

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports
from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)
from apex.apex_core.setup.seeders.portal_identity_seed import seed_portal_identities


ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

KEPT_GENDERS = ("Male", "Female")

def after_install():
    frappe.db.commit()
    create_accommodation_item_defaults(allow_deferred=True)
    seed_templates()
    seed_auto_email_reports()
    seed_portal_identities()
    restrict_genders()
    frappe.clear_cache()


def after_migrate():
    seed_portal_identities()
    seed_templates()
    return create_accommodation_item_defaults(allow_deferred=True)


def create_accommodation_item_defaults(*, allow_deferred=False):
    item_group_root = _get_item_group_root()
    if not item_group_root:
        if allow_deferred:
            return False
        raise frappe.DoesNotExistError(
            _("ERPNext Item Group root is required before seeding accommodation items.")
        )

    create_accommodation_item_groups(item_group_root)
    create_accommodation_items()
    return True


def _get_item_group_root():
    roots = frappe.get_all(
        "Item Group",
        filters={"parent_item_group": ["is", "not set"]},
        pluck="name",
    )
    if len(roots) > 1:
        raise NestedSetMultipleRootsError(_("Multiple root nodes not allowed."))
    return roots[0] if roots else None


def create_accommodation_item_groups(item_group_root):

    root_lft, root_rgt = frappe.db.get_value(
        "Item Group",
        item_group_root,
        ["lft", "rgt"],
    )
    if root_lft is None or root_rgt is None or root_lft >= root_rgt:
        rebuild_tree("Item Group", "parent_item_group")

    for group in ACCOMMODATION_ITEM_GROUPS:
        exists = frappe.db.exists("Item Group", group)
        existing_parent = frappe.db.get_value("Item Group", group, "parent_item_group")
        parent_is_group = (
            frappe.db.get_value("Item Group", existing_parent, "is_group")
            if existing_parent
            else False
        )
        if exists and parent_is_group:
            continue
        if exists:
            doc = frappe.get_doc("Item Group", group)
            doc.parent_item_group = item_group_root
            doc.save()
        else:
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": group,
                    "parent_item_group": item_group_root,
                    "is_group": 0,
                }
            ).insert()


def restrict_genders():
    surplus = [
        name for name in frappe.get_all("Gender", pluck="name") if name not in KEPT_GENDERS
    ]
    removed, kept = [], []
    for name in surplus:
        try:
            frappe.delete_doc("Gender", name)
            removed.append(name)
        except frappe.LinkExistsError:
            kept.append(name)
    if kept:
        print(f"apex: Gender still in use, left in place: {kept}")
    return {"removed": removed, "in_use": kept}


def create_accommodation_items():
    for record in _load_accommodation_item_records():
        if frappe.db.exists("Item", record["item_code"]):
            continue
        frappe.get_doc(record).insert()


def _load_accommodation_item_records():
    data_path = frappe.get_app_path(
        "apex",
        "apex_core",
        "setup",
        "accommodation_items.json",
    )
    with open(data_path, encoding="utf-8") as source:
        return json.load(source)


