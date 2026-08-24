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
    create_roles()
    frappe.db.commit()
    create_role_profiles()
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
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": group,
                    "parent_item_group": item_group_root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)


def restrict_genders():
    surplus = [
        name for name in frappe.get_all("Gender", pluck="name") if name not in KEPT_GENDERS
    ]
    removed, kept = [], []
    for name in surplus:
        try:
            frappe.delete_doc("Gender", name, ignore_permissions=True)
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
        frappe.get_doc(record).insert(ignore_permissions=True)


def _load_accommodation_item_records():
    data_path = frappe.get_app_path(
        "apex",
        "apex_core",
        "setup",
        "accommodation_items.json",
    )
    with open(data_path, encoding="utf-8") as source:
        return json.load(source)


def create_roles():
    if not frappe.db.exists("Role", "Admin Manager"):
        doc = frappe.new_doc("Role")
        doc.role_name = "Admin Manager"
        doc.desk_access = 0
        doc.insert(ignore_permissions=True)


def create_role_profiles():
    profiles = {
        "Habitat Accommodation Manager": ["Accommodation Manager"],
        "Habitat Resident Supervisor": ["Resident Supervisor"],
        "Habitat Finance Reviewer": ["Finance Manager", "Internal Auditor"],
        "Habitat Maintenance Technician": ["Maintenance Technician"],
        "Habitat Cleaning Supervisor": ["Cleaning Supervisor"],
        "Habitat Safety Officer": ["Safety Officer"],
        "Habitat Resident Request Coordinator": ["Resident Request Coordinator"],
    }
    for profile_name, roles in profiles.items():
        if not frappe.db.exists("Role Profile", profile_name):
            doc = frappe.new_doc("Role Profile")
            doc.role_profile = profile_name
            for role in roles:
                doc.append("roles", {"role": role})
            doc.insert(ignore_permissions=True)
            doc.unlock()
    if not frappe.db.exists("Role Profile", "Salis Driver"):
        doc = frappe.new_doc("Role Profile")
        doc.role_profile = "Salis Driver"
        doc.append("roles", {"role": "Driver"})
        doc.insert(ignore_permissions=True)
        doc.unlock()

