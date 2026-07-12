# Copyright (c) 2026, AFMCO and contributors
import frappe

from apex.apex_core.setup.seeders.habitat_auto_email_reports_seed import seed_auto_email_reports
from apex.apex_core.setup.seeders.habitat_dashboard_seed import (
    seed_habitat_dashboard,
    seed_role_dashboards,
)
from apex.habitat.doctype.maintenance_material.maintenance_material_catalog import (
    seed_catalog,
)
from apex.apex_core.setup.seeders.maintenance_material_template_seed import (
    seed_templates,
)

# [#1e17u4]


def after_install():
    create_roles()
    frappe.db.commit()  # [#93zbw7]
    create_role_profiles()
    create_custody_asset_categories()
    create_custody_articles()
    create_operational_depreciation_policies()
    create_safety_task_catalogs()
    seed_catalog()
    seed_templates()
    seed_auto_email_reports()
    seed_habitat_dashboard()
    seed_role_dashboards()
    # [#d3h8rl]
    frappe.clear_cache()


def create_roles():
    roles = [
        "Accommodation Manager",
        "Resident Supervisor",
        "Finance Manager",
        "Internal Auditor",
        "Maintenance Technician",
        "Cleaning Supervisor",
        "Safety Officer",
        "Resident Request Coordinator",
        "Admin Manager",
        "Operations Director",
        "Facilities Supervisor",
        "Procurement Supervisor",
    ]
    for role_name in roles:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.new_doc("Role")
            doc.role_name = role_name
            doc.desk_access = 1
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
        if not frappe.db.exists("Custody Article", article["article_name"]):
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
