# Copyright (c) 2026, AFMCO and contributors
import json

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSetMultipleRootsError, rebuild_tree

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports
from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)

# [#1e17u4]

ACCOMMODATION_ITEM_GROUPS = [
    "Accommodation Bedding",
    "Accommodation Furniture",
    "Accommodation Appliances",
    "Accommodation Kitchenware",
    "Accommodation Sanitary and Cleaning",
]

def after_install():
    create_roles()
    frappe.db.commit()  # [#93zbw7]
    create_role_profiles()
    create_accommodation_item_defaults(allow_deferred=True)
    create_custody_asset_categories()
    create_custody_articles()
    create_operational_depreciation_policies()
    create_safety_task_catalogs()
    # Single call: seed_templates owns both Maintenance Material writers and runs
    # them first, so the templates' REQUIRED child Links can never dangle here.
    seed_templates()
    seed_auto_email_reports()
    # [#d3h8rl]
    frappe.clear_cache()


def after_migrate():
    """Recover item defaults on configured sites without blocking incomplete sites."""
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
            doc.save(ignore_permissions=True)  # audit-ok
        else:
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": group,
                    "parent_item_group": item_group_root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)  # audit-ok


def create_accommodation_items():
    """Insert the accommodation Items after their Item Groups are available."""
    for record in _load_accommodation_item_records():
        if frappe.db.exists("Item", record["item_code"]):
            continue
        frappe.get_doc(record).insert(ignore_permissions=True)  # audit-ok


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
    # (role_name, desk_access). Native-first provisioning of the app's Roles (the
    # Role fixture was retired — it re-locked the Role Profile queue_action on every
    # worker-less migrate). hooks.py lists this in after_install (via after_install
    # above) AND directly in after_migrate, so the roles are durable on every migrate
    # — unlike the Salis seed_salis_* roles, which salis.setup.after_install runs once
    # at install and patches.txt then replays only on already-installed sites.
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
        # SIM Operations business role (telecom / SIM custody operators).
        ("SIM Operations User", 1),
        # Fleet approval role (Movement Cost Transfer / Vehicle Damage Write-Off
        # workflows). Provisioned here too so the approver role is always present.
        ("Fleet Manager", 1),
        # Field-worker role: NO desk access (native Website User isolation keeps the
        # whole desk module list off a driver). Must exist before create_role_profiles
        # builds the Salis Driver profile below.
        ("Driver", 0),
    ]
    for role_name, desk_access in roles:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.new_doc("Role")
            doc.role_name = role_name
            doc.desk_access = desk_access
            doc.insert(ignore_permissions=True)


def create_role_profiles():
    profiles = {
        # [#gb52vh]
        "Habitat Accommodation Manager": ["Accommodation Manager"],
        "Habitat Resident Supervisor": ["Resident Supervisor"],
        "Habitat Finance Reviewer": ["Finance Manager", "Internal Auditor"],
        # [#aeif1q]
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
            # [#7cx306]
            doc.unlock()
    # [#a036rp]
    # A-036: native provisioning of the Salis field-worker Role Profile bundling
    # the desk_access=0 Driver role (was a fixture, which re-fired Role Profile's
    # core on_update queue_action file lock on every worker-less migrate ->
    # DocumentLockedError). Same exists-guard + insert + unlock pattern as above:
    # skipped when it already exists, so re-runs never re-lock the doc.
    if not frappe.db.exists("Role Profile", "Salis Driver"):
        doc = frappe.new_doc("Role Profile")
        doc.role_profile = "Salis Driver"
        doc.append("roles", {"role": "Driver"})
        doc.insert(ignore_permissions=True)
        doc.unlock()


def create_custody_asset_categories():
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
        # Filter, not a name probe: Custody Article autonames by naming_series, so a
        # probe keyed on the name never matches and every run re-inserts all ten.
        if not frappe.db.exists("Custody Article", {"article_name": article["article_name"]}):
            doc = frappe.new_doc("Custody Article")
            doc.update(article)
            doc.insert(ignore_permissions=True)


def create_operational_depreciation_policies():
    # [#devsf7]
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


def create_safety_task_catalogs():
    # [#saqivo]
    tasks = [
        {"task_code": "SAF-001", "task_title": "Daily Cleanliness Assessment", "department": "Health and Hygiene", "frequency": "Daily", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check common areas, corridors, and bathrooms for cleanliness."},
        {"task_code": "SAF-002", "task_title": "Daily Exit Obstruction Check", "department": "Fire Safety", "frequency": "Daily", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Ensure all emergency exits and fire doors are clear of obstructions."},
        {"task_code": "SAF-003", "task_title": "Weekly Fire Extinguisher Check", "department": "Fire Safety", "frequency": "Weekly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check fire extinguishers for pressure, pin, and tag."},
        {"task_code": "SAF-004", "task_title": "Weekly First Aid Kit Inspection", "department": "Health and Hygiene", "frequency": "Weekly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check inventory and expiration dates of first aid kits."},
        {"task_code": "SAF-005", "task_title": "Weekly Emergency Signage Check", "department": "Fire Safety", "frequency": "Weekly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Verify all emergency exit signs are illuminated and visible."},
        {"task_code": "SAF-006", "task_title": "Monthly Water Tank Inspection", "department": "Health and Hygiene", "frequency": "Monthly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Inspect water tanks for leaks, cleanliness, and structural integrity."},
        {"task_code": "SAF-007", "task_title": "Monthly CCTV Recording Verification", "department": "Security", "frequency": "Monthly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Ensure all CCTV cameras are functional and recording properly."},
        {"task_code": "SAF-008", "task_title": "Monthly Fire Alarm Panel Check", "department": "Fire Safety", "frequency": "Monthly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Test fire alarm panel indicators and verify no fault conditions."},
        {"task_code": "SAF-009", "task_title": "Quarterly Pest Control", "department": "Health and Hygiene", "frequency": "Quarterly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Perform scheduled pest control spray across all rooms and facilities."},
        {"task_code": "SAF-010", "task_title": "Annual License Renewal Follow-up", "department": "Compliance and Licensing", "frequency": "Annual", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check civil defense and municipal licenses and initiate renewal if within 90 days."},
    ]
    for task in tasks:
        if not frappe.db.exists("Safety Task Catalog", {"task_code": task["task_code"]}):
            doc = frappe.new_doc("Safety Task Catalog")
            doc.update(task)
            doc.insert(ignore_permissions=True)
