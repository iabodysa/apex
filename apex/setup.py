# Copyright (c) 2026, afmcoltd
"""Install-time and migrate-time setup for the app.

Everything here runs from the ``after_install`` / ``after_migrate`` hooks, under Administrator,
against a site that has no operator on it yet. That is why the writes pass ``ignore_permissions``:
there is no session user whose roles could be consulted, and a DocPerm added to make these saves
legal would then also be live for every real operator afterwards. This is the installer context —
it is the rare case the rule allows, not a shortcut around a missing role.
"""
import json

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSetMultipleRootsError, rebuild_tree

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports
from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)
from apex.apex_core.setup.seeders.letter_head_seed import seed_letter_head
from apex.apex_core.setup.seeders.portal_identity_seed import seed_portal_identities
from apex.apex_core.setup.seeders.workspace_role_seed import seed_workspace_roles


ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

KEPT_GENDERS = ("Male", "Female")

def after_install():
    """Runs the after-install seed: roles, profiles, item defaults, custody masters, and policies."""
    create_roles()
    frappe.db.commit()
    create_role_profiles()
    create_accommodation_item_defaults(allow_deferred=True)
    create_custody_asset_categories()
    create_custody_articles()
    create_operational_depreciation_policies()
    seed_templates()
    seed_auto_email_reports()
    seed_workspace_roles()
    seed_letter_head()
    seed_portal_identities()
    restrict_genders()
    frappe.clear_cache()


def after_migrate():
    """Recover item defaults on configured sites without blocking incomplete sites."""
    seed_workspace_roles()
    seed_letter_head()
    seed_portal_identities()
    return create_accommodation_item_defaults(allow_deferred=True)


def create_accommodation_item_defaults(*, allow_deferred=False):
    """Seed accommodation Item Groups and Items once ERPNext has its root."""
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
    """Returns the single root Item Group, or None when ERPNext has not created one yet."""
    roots = frappe.get_all(
        "Item Group",
        filters={"parent_item_group": ["is", "not set"]},
        pluck="name",
    )
    if len(roots) > 1:
        raise NestedSetMultipleRootsError(_("Multiple root nodes not allowed."))
    return roots[0] if roots else None


def create_accommodation_item_groups(item_group_root):
    """Create accommodation groups under the installed ERPNext root."""

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
    """Leave only Male and Female on the site, keeping any Gender a record still points at.

    ``frappe.desk.page.setup_wizard.install_fixtures.update_genders`` creates seven Genders at
    setup time. Apex offers two, so the surplus is removed once — at install for a new site and
    by a patch for a site that already ran the wizard. It is deliberately absent from
    ``after_migrate``: a Gender an operator adds later is theirs, and a migrate that deleted it
    every run would be the app arguing with its own operator.

    Deletion goes through ``frappe.delete_doc``, so the framework's own link check decides what
    may go. A Gender still referenced by an Employee survives and is reported, rather than
    being forced out from under the row that uses it.
    """
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
        frappe.logger().info(f"apex: Gender still in use, left in place: {kept}")
    return {"removed": removed, "in_use": kept}


def create_accommodation_items():
    """Insert the accommodation Items after their Item Groups are available."""
    for record in _load_accommodation_item_records():
        if frappe.db.exists("Item", record["item_code"]):
            continue
        frappe.get_doc(record).insert(ignore_permissions=True)


def _load_accommodation_item_records():
    """Loads the bundled accommodation Item records from their JSON fixture file."""
    data_path = frappe.get_app_path(
        "apex",
        "apex_core",
        "setup",
        "accommodation_items.json",
    )
    with open(data_path, encoding="utf-8") as source:
        return json.load(source)


def create_roles():
    """Creates each standing Apex role that does not already exist."""
    roles = [
        ("Accommodation Manager", 1),
        ("Resident Supervisor", 1),
        ("Finance Manager", 1),
        ("Internal Auditor", 1),
        ("Maintenance Technician", 1),
        ("Cleaning Supervisor", 1),
        ("Safety Officer", 1),
        ("Resident Request Coordinator", 1),
        ("Admin Manager", 1),
        ("Operations Director", 1),
        ("Facilities Supervisor", 1),
        ("Procurement Supervisor", 1),
        ("SIM Operations User", 1),
        ("Fleet Manager", 1),
        ("Driver", 0),
    ]
    for role_name, desk_access in roles:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.new_doc("Role")
            doc.role_name = role_name
            doc.desk_access = desk_access
            doc.insert(ignore_permissions=True)


def create_role_profiles():
    """Creates the standing Habitat and Salis Role Profiles that bundle roles for onboarding."""
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


def create_custody_asset_categories():
    """Creates each standing Custody Asset Category that does not already exist."""
    categories = [
        "Bedding & Linen",
        "Room Access",
        "Remote Controls",
        "Furniture",
        "Cleaning Tools",
        "Safety Equipment",
        "Facility Keys",
    ]
    for category_name in categories:
        if not frappe.db.exists("Custody Asset Category", category_name):
            doc = frappe.new_doc("Custody Asset Category")
            doc.category_name = category_name
            doc.insert(ignore_permissions=True)


def create_custody_articles():
    """Creates each standing returnable Custody Article under its category."""
    articles = [
        {"article_name": "Room Key", "category": "Room Access", "is_returnable": 1},
        {"article_name": "Gate Access Card", "category": "Room Access", "is_returnable": 1},
        {"article_name": "Locker Key", "category": "Room Access", "is_returnable": 1},
        {"article_name": "Blanket", "category": "Bedding & Linen", "is_returnable": 1},
        {"article_name": "Pillow", "category": "Bedding & Linen", "is_returnable": 1},
        {"article_name": "Bed Sheet", "category": "Bedding & Linen", "is_returnable": 1},
        {"article_name": "Mattress Protector", "category": "Bedding & Linen", "is_returnable": 1},
        {"article_name": "AC Remote", "category": "Remote Controls", "is_returnable": 1},
        {"article_name": "TV Remote", "category": "Remote Controls", "is_returnable": 1},
        {"article_name": "Padlock", "category": "Facility Keys", "is_returnable": 1},
    ]
    for article in articles:
        if not frappe.db.exists("Custody Article", {"article_name": article["article_name"]}):
            doc = frappe.new_doc("Custody Article")
            doc.update(article)
            doc.insert(ignore_permissions=True)


def create_operational_depreciation_policies():
    """Creates each standing Operational Depreciation Policy with its useful life."""
    policies = [
        {"policy_name": "Linen - 12 Months", "useful_life_years": 1},
        {"policy_name": "Keys and Cards - 24 Months", "useful_life_years": 2},
        {"policy_name": "Remotes - 24 Months", "useful_life_years": 2},
        {"policy_name": "Furniture - 36 Months", "useful_life_years": 3},
        {"policy_name": "Electronics - 36 Months", "useful_life_years": 3},
    ]
    for policy in policies:
        if not frappe.db.exists("Operational Depreciation Policy", policy["policy_name"]):
            doc = frappe.new_doc("Operational Depreciation Policy")
            doc.update(policy)
            doc.insert(ignore_permissions=True)
