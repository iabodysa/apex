import frappe
from apex_habitat.habitat.doctype.maintenance_material_template.maintenance_material_template_seed import seed_templates

from apex_habitat.habitat.doctype.maintenance_material.maintenance_material_catalog import seed_catalog

from apex_habitat.habitat.notifications_seed import seed_operational_notifications
from apex_habitat.habitat.kanban_seed import seed_kanban_boards
from apex_habitat.habitat.assignment_rules_seed import seed_assignment_rules
from apex_habitat.habitat.auto_email_reports_seed import seed_auto_email_reports
from apex_habitat.habitat.email_templates_seed import seed_email_templates
from apex_habitat.habitat.dashboard_seed import seed_habitat_dashboard, seed_role_dashboards


def after_install():
    create_roles()
    create_role_profiles()
    create_custody_asset_categories()
    create_custody_articles()
    create_operational_depreciation_policies()
    create_safety_task_catalogs()
    seed_catalog()
    seed_templates()
    seed_operational_notifications()
    seed_kanban_boards()
    seed_assignment_rules()
    seed_auto_email_reports()
    seed_email_templates()
    seed_habitat_dashboard()
    seed_role_dashboards()
    # Force translation cache reload so Arabic strings appear on first login
    frappe.clear_cache()


def create_roles():
    roles = [
        "Accommodation Manager",
        "Resident Supervisor",
        "Finance Manager",
        "Internal Auditor",
    ]
    for role_name in roles:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.new_doc("Role")
            doc.role_name = role_name
            doc.desk_access = 1
            doc.insert(ignore_permissions=True)


def create_role_profiles():
    profiles = {
        "Habitat Accommodation Manager": ["Accommodation Manager", "System Manager"],
        "Habitat Resident Supervisor": ["Resident Supervisor"],
        "Habitat Finance Reviewer": ["Finance Manager", "Internal Auditor"],
    }
    for profile_name, roles in profiles.items():
        if not frappe.db.exists("Role Profile", profile_name):
            doc = frappe.new_doc("Role Profile")
            doc.role_profile = profile_name
            for role in roles:
                doc.append("roles", {"role": role})
            doc.insert(ignore_permissions=True)


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
    # Note: DocType field is `useful_life_years` (Int), so the durations below
    # are expressed in whole years. Sub-year policies (e.g. linen at 12 months)
    # are rounded up to 1 year to satisfy the mandatory Int field.
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
    # task_code must be unique; used as deduplication key
    # frequency must match DocType Select options: Daily/Weekly/Monthly/Quarterly/Annual/As Needed/On Entry
    # priority must match: High/Medium/Low
    tasks = [
        {"task_code": "SAF-001", "task_title": "Daily Cleanliness Assessment", "task_title_en": "Daily Cleanliness Assessment", "department": "Health & Hygiene", "frequency": "Daily", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check common areas, corridors, and bathrooms for cleanliness."},
        {"task_code": "SAF-002", "task_title": "Daily Exit Obstruction Check", "task_title_en": "Daily Exit Obstruction Check", "department": "Fire Safety", "frequency": "Daily", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Ensure all emergency exits and fire doors are clear of obstructions."},
        {"task_code": "SAF-003", "task_title": "Weekly Fire Extinguisher Check", "task_title_en": "Weekly Fire Extinguisher Check", "department": "Fire Safety", "frequency": "Weekly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check fire extinguishers for pressure, pin, and tag."},
        {"task_code": "SAF-004", "task_title": "Weekly First Aid Kit Inspection", "task_title_en": "Weekly First Aid Kit Inspection", "department": "Health & Hygiene", "frequency": "Weekly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check inventory and expiration dates of first aid kits."},
        {"task_code": "SAF-005", "task_title": "Weekly Emergency Signage Check", "task_title_en": "Weekly Emergency Signage Check", "department": "Fire Safety", "frequency": "Weekly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Verify all emergency exit signs are illuminated and visible."},
        {"task_code": "SAF-006", "task_title": "Monthly Water Tank Inspection", "task_title_en": "Monthly Water Tank Inspection", "department": "Health & Hygiene", "frequency": "Monthly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Inspect water tanks for leaks, cleanliness, and structural integrity."},
        {"task_code": "SAF-007", "task_title": "Monthly CCTV Recording Verification", "task_title_en": "Monthly CCTV Recording Verification", "department": "Security", "frequency": "Monthly", "priority": "Medium", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Ensure all CCTV cameras are functional and recording properly."},
        {"task_code": "SAF-008", "task_title": "Monthly Fire Alarm Panel Check", "task_title_en": "Monthly Fire Alarm Panel Check", "department": "Fire Safety", "frequency": "Monthly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Test fire alarm panel indicators and verify no fault conditions."},
        {"task_code": "SAF-009", "task_title": "Quarterly Pest Control", "task_title_en": "Quarterly Pest Control", "department": "Health & Hygiene", "frequency": "Quarterly", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Perform scheduled pest control spray across all rooms and facilities."},
        {"task_code": "SAF-010", "task_title": "Annual License Renewal Follow-up", "task_title_en": "Annual License Renewal Follow-up", "department": "Compliance & Licensing", "frequency": "Annual", "priority": "High", "applicable_to_all_buildings": 1, "is_active": 1, "instructions": "Check civil defense and municipal licenses and initiate renewal if within 90 days."},
    ]
    for task in tasks:
        if not frappe.db.exists("Safety Task Catalog", {"task_code": task["task_code"]}):
            doc = frappe.new_doc("Safety Task Catalog")
            doc.update(task)
            doc.insert(ignore_permissions=True)
