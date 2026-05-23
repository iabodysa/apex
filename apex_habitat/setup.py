import frappe


def after_install():
    create_roles()
    create_role_profiles()
    create_custody_asset_categories()
    create_custody_articles()
    create_operational_depreciation_policies()
    create_safety_task_catalogs()


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
    policies = [
        {"policy_name": "Linen - 12 Months", "useful_life_months": 12},
        {"policy_name": "Keys and Cards - 24 Months", "useful_life_months": 24},
        {"policy_name": "Remotes - 24 Months", "useful_life_months": 24},
        {"policy_name": "Furniture - 36 Months", "useful_life_months": 36},
        {"policy_name": "Electronics - 36 Months", "useful_life_months": 36},
    ]
    for policy in policies:
        if not frappe.db.exists("Operational Depreciation Policy", policy["policy_name"]):
            doc = frappe.new_doc("Operational Depreciation Policy")
            doc.update(policy)
            doc.insert(ignore_permissions=True)


def create_safety_task_catalogs():
    tasks = [
        {"task_name": "Daily Cleanliness Assessment", "frequency": "Daily", "priority": "Medium", "instructions": "Check common areas, corridors, and bathrooms for cleanliness."},
        {"task_name": "Daily Exit Obstruction Check", "frequency": "Daily", "priority": "High", "instructions": "Ensure all emergency exits and fire doors are clear of obstructions."},
        {"task_name": "Weekly Fire Extinguisher Check", "frequency": "Weekly", "priority": "High", "instructions": "Check fire extinguishers for pressure, pin, and tag."},
        {"task_name": "Weekly First Aid Kit Inspection", "frequency": "Weekly", "priority": "Medium", "instructions": "Check inventory and expiration dates of first aid kits."},
        {"task_name": "Monthly Water Tank Inspection", "frequency": "Monthly", "priority": "High", "instructions": "Inspect water tanks for leaks, cleanliness, and structural integrity."},
        {"task_name": "Monthly CCTV Recording Verification", "frequency": "Monthly", "priority": "Medium", "instructions": "Ensure all CCTV cameras are functional and recording properly."},
        {"task_name": "Quarterly Pest Control", "frequency": "Quarterly", "priority": "High", "instructions": "Perform scheduled pest control spray across all rooms and facilities."},
        {"task_name": "Annual License Renewal Follow-up", "frequency": "Annually", "priority": "Critical", "instructions": "Check civil defense and municipal licenses and initiate renewal if within 90 days."},
    ]
    for task in tasks:
        if not frappe.db.exists("Safety Task Catalog", task["task_name"]):
            doc = frappe.new_doc("Safety Task Catalog")
            doc.update(task)
            doc.insert(ignore_permissions=True)
