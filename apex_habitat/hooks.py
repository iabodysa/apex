app_name = "apex_habitat"
app_title = "Apex Habitat"
app_publisher = "Abdullah Fahad Al-Mutairi Co. (AFMCO)"
app_description = "Accommodation and facilities management application."
app_email = "afm@afmcoltd.com"
app_license = "MIT"

# Required Frappe apps
required_apps = ["frappe", "erpnext", "hrms"]

# Frappe v15: export type annotations in DocType controllers when supported
export_python_type_annotations = True

app_version = "0.6.0"

# Theme inclusions
app_include_css = "/assets/apex_habitat/css/afmco_theme.css"
web_include_css = "/assets/apex_habitat/css/afmco_theme.css"

# Single functional module: Habitat

# Document lifecycle hooks
doc_events = {
    "Accommodation Building": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.before_save",
    },
    "Accommodation Assignment": {
        "validate": "apex_habitat.habitat.doctype.accommodation_assignment.accommodation_assignment.validate",
        "on_submit": "apex_habitat.habitat.doctype.accommodation_assignment.accommodation_assignment.on_submit",
        "on_cancel": "apex_habitat.habitat.doctype.accommodation_assignment.accommodation_assignment.on_cancel",
    },
    "Accommodation Checkout": {
        "validate": "apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout.validate",
        "on_submit": "apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout.before_cancel",
        "on_cancel": "apex_habitat.habitat.doctype.accommodation_checkout.accommodation_checkout.on_cancel",
    },
    "Accommodation Lease": {
        "validate": "apex_habitat.habitat.doctype.accommodation_lease.accommodation_lease.validate",
    },
    "Utility Bill Entry": {
        "validate": "apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry.validate",
        "on_submit": "apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.utility_bill_entry.utility_bill_entry.before_cancel",
    },
    # Safety Inspection Report and Safety Task Execution doc_events registered in Phase 7.
    # Phase 5 — Custody and Operational Depreciation
    "Custody Issue": {
        "validate": "apex_habitat.habitat.doctype.custody_issue.custody_issue.validate",
        "on_submit": "apex_habitat.habitat.doctype.custody_issue.custody_issue.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.custody_issue.custody_issue.before_cancel",
        "on_cancel": "apex_habitat.habitat.doctype.custody_issue.custody_issue.on_cancel",
    },
    "Custody Return": {
        "validate": "apex_habitat.habitat.doctype.custody_return.custody_return.validate",
        "on_submit": "apex_habitat.habitat.doctype.custody_return.custody_return.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.custody_return.custody_return.before_cancel",
        "on_cancel": "apex_habitat.habitat.doctype.custody_return.custody_return.on_cancel",
    },
    "Custody Damage Assessment": {
        "validate": "apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment.validate",
        "on_submit": "apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment.before_cancel",
    },
    "Non-Financial Depreciation Snapshot": {
        "validate": "apex_habitat.habitat.doctype.non_financial_depreciation_snapshot.non_financial_depreciation_snapshot.validate",
        "before_cancel": "apex_habitat.habitat.doctype.non_financial_depreciation_snapshot.non_financial_depreciation_snapshot.before_cancel",
    },
    # Phase 6 gaps
    "Facility Asset Movement": {
        "validate": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
        "on_submit": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.before_cancel",
    },
    "Maintenance Work Order": {
        "validate": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.validate",
        "on_submit": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.before_cancel",
    },
    # Phase 7 gaps
    "Scheduled Task Instance": {
        "validate": "apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance.validate",
        "on_submit": "apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.scheduled_task_instance.scheduled_task_instance.before_cancel",
    },
    "Maintenance Inspection Report": {
        "validate": "apex_habitat.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report.validate",
        "before_cancel": "apex_habitat.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report.before_cancel",
    },
}

# Scheduled tasks
scheduler_events = {
    "daily": [
        "apex_habitat.habitat.tasks.daily_accommodation_cost_allocation",
        "apex_habitat.habitat.tasks.daily_building_license_expiry_check",
        "apex_habitat.habitat.tasks.open_maintenance_escalation",
        "apex_habitat.habitat.tasks.lease_expiry_watchlist",
        "apex_habitat.habitat.tasks.daily_scheduled_task_instance_generator",
    ],
    "weekly": [
        "apex_habitat.habitat.tasks.weekly_occupancy_sync",
        "apex_habitat.habitat.tasks.weekly_safety_task_compliance_scan",
    ],
    "monthly": [
        "apex_habitat.habitat.tasks.monthly_rent_due_alert",
    ],
}

# Employee form dashboard: surface housing and custody records
override_doctype_dashboards = {
    "Employee": "apex_habitat.habitat.api.employee_links.get_data",
}

# Fixtures shipped with the app
fixtures = [
    {"dt": "Safety Task Catalog"},
    {"dt": "Role", "filters": [["name", "in", ["Accommodation Manager", "Resident Supervisor", "Finance Manager", "Internal Auditor"]]]},
    # Print Format and Web Form are standard module files (is_standard=1)
    # under habitat/print_format/ and habitat/web_form/ — loaded automatically
    # by bench migrate via import_file, no fixture entry needed.
]

after_install = "apex_habitat.setup.after_install"

# Frappe What's New feed — appears in desk notification area, not as a popup
get_changelog_feed = "apex_habitat.habitat.utils.changelog.get_changelog_feed"
