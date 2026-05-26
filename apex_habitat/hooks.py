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


# Single functional module: Habitat

# Document lifecycle hooks
doc_events = {
    "Accommodation Site": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_site.accommodation_site.before_save",
    },
    "Accommodation Bed": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_bed.accommodation_bed.before_save",
    },
    "Accommodation Room": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_room.accommodation_room.before_save",
    },
    "Accommodation QR Location": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_qr_location.accommodation_qr_location.before_save",
    },
    "Accommodation Ledger": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_ledger.accommodation_ledger.before_save",
    },
    "Accommodation Resident Request": {
        "before_insert": "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.before_insert",
        "validate": "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.validate",
        "on_update": "apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request.on_update",
    },
    "Building License": {
        "before_save": "apex_habitat.habitat.doctype.building_license.building_license.before_save",
    },
    "Camera Access Grant": {
        "before_save": "apex_habitat.habitat.doctype.camera_access_grant.camera_access_grant.before_save",
    },
    "Cleaning Log": {
        "before_save": "apex_habitat.habitat.doctype.cleaning_log.cleaning_log.before_save",
    },
    "Client Audit Remediation Plan": {
        "before_save": "apex_habitat.habitat.doctype.client_audit_remediation_plan.client_audit_remediation_plan.before_save",
    },
    "Scheduled Task Template": {
        "before_save": "apex_habitat.habitat.doctype.scheduled_task_template.scheduled_task_template.before_save",
    },
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
    "Room Bed Transfer": {
        "validate": "apex_habitat.habitat.doctype.room_bed_transfer.room_bed_transfer.validate",
        "on_submit": "apex_habitat.habitat.doctype.room_bed_transfer.room_bed_transfer.on_submit",
        "on_cancel": "apex_habitat.habitat.doctype.room_bed_transfer.room_bed_transfer.on_cancel",
    },
    "Safety Inspection Report": {
        "before_save": "apex_habitat.habitat.doctype.safety_inspection_report.safety_inspection_report.before_save",
    },
    "Maintenance Request": {
        "before_save": "apex_habitat.habitat.doctype.maintenance_request.maintenance_request.before_save",
    },
    "Custody Article": {
        "before_save": "apex_habitat.habitat.doctype.custody_article.custody_article.before_save",
    },
    "Custody Asset Category": {
        "before_save": "apex_habitat.habitat.doctype.custody_asset_category.custody_asset_category.before_save",
    },
    # Phase 5 — Custody and Operational Depreciation
    "Idle Resident Report": {
        "validate": "apex_habitat.habitat.doctype.idle_resident_report.idle_resident_report.validate",
        "after_insert": "apex_habitat.habitat.doctype.idle_resident_report.idle_resident_report.after_insert",
    },
    "Accommodation Material Transfer": {
        "validate": "apex_habitat.habitat.doctype.accommodation_material_transfer.accommodation_material_transfer.validate",
        "on_submit": "apex_habitat.habitat.doctype.accommodation_material_transfer.accommodation_material_transfer.on_submit",
        "on_cancel": "apex_habitat.habitat.doctype.accommodation_material_transfer.accommodation_material_transfer.on_cancel",
    },
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
    "Facility Asset": {
        "before_save": "apex_habitat.habitat.doctype.facility_asset.facility_asset.before_save",
    },
    "Facility Asset Custody Assignment": {
        "before_save": "apex_habitat.habitat.doctype.facility_asset_custody_assignment.facility_asset_custody_assignment.before_save",
    },
    "Facility Asset Movement": {
        "before_save": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.before_save",
        "validate": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
        "on_submit": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.before_cancel",
    },
    "Operational Depreciation Policy": {
        "before_save": "apex_habitat.habitat.doctype.operational_depreciation_policy.operational_depreciation_policy.before_save",
    },
    "Subcontractor Service Order": {
        "before_save": "apex_habitat.habitat.doctype.subcontractor_service_order.subcontractor_service_order.before_save",
    },
    "Subcontractor Service Contract": {
        "before_save": "apex_habitat.habitat.doctype.subcontractor_service_contract.subcontractor_service_contract.before_save",
    },
    "Utility Account": {
        "before_save": "apex_habitat.habitat.doctype.utility_account.utility_account.before_save",
    },
    "Habitat Settings": {
        "before_save": "apex_habitat.habitat.doctype.habitat_settings.habitat_settings.before_save",
    },
    "Safety Task Catalog": {
        "before_save": "apex_habitat.habitat.doctype.safety_task_catalog.safety_task_catalog.before_save",
    },
    "Safety Task Execution": {
        "before_save": "apex_habitat.habitat.doctype.safety_task_execution.safety_task_execution.before_save",
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
        "apex_habitat.habitat.tasks.temporary_stay_checkout_watchlist",
        "apex_habitat.habitat.tasks.idle_resident_aging",
        "apex_habitat.habitat.tasks.daily_scheduled_task_instance_generator",
        "apex_habitat.habitat.tasks.daily_occupancy_snapshot",
        # Salis fleet module
        "apex_habitat.salis.tasks.driver_license_expiry_watch",
        "apex_habitat.salis.tasks.idle_vehicle_watch",
        "apex_habitat.salis.tasks.unreverted_topup_watch",
        "apex_habitat.salis.tasks.overdue_fuel_request_watch",
        "apex_habitat.salis.tasks.missing_attendance_watch",
        "apex_habitat.salis.tasks.vehicle_compliance_expiry_watch",
        "apex_habitat.salis.fuel_engine.accrue_fuel_consumption",
        "apex_habitat.salis.rental_engine.daily_rental_accrual",
    ],
    "weekly": [
        "apex_habitat.habitat.tasks.weekly_occupancy_sync",
        "apex_habitat.habitat.tasks.weekly_safety_task_compliance_scan",
        "apex_habitat.salis.tasks.vehicle_utilization_summary",
        "apex_habitat.salis.utilisation_engine.weekly_vehicle_utilisation_snapshot",
    ],
    "monthly": [
        "apex_habitat.habitat.tasks.monthly_rent_due_alert",
        "apex_habitat.salis.fuel_engine.monthly_fuel_reconciliation",
    ],
}

# Employee form dashboard: surface housing and custody records
override_doctype_dashboards = {
    "Employee": "apex_habitat.habitat.api.employee_links.get_data",
    "Supplier": "apex_habitat.habitat.api.supplier_links.get_data",
}

# Salis: project-based row scoping (tiered authority) — supervisors/PMs see only
# the projects they hold a User Permission for; oversight roles see all.
permission_query_conditions = {
    "Vehicle Assignment": "apex_habitat.salis.permissions.vehicle_assignment_query",
    "Fuel Request": "apex_habitat.salis.permissions.fuel_request_query",
    "Fuel Topup Request": "apex_habitat.salis.permissions.fuel_topup_request_query",
    "Dispatch Trip": "apex_habitat.salis.permissions.dispatch_trip_query",
    "Transport Request": "apex_habitat.salis.permissions.transport_request_query",
    "Route Plan": "apex_habitat.salis.permissions.route_plan_query",
    "Sponsorship Transfer Case": "apex_habitat.salis.permissions.sponsorship_transfer_case_query",
}

has_permission = {
    "Vehicle Assignment": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Topup Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Dispatch Trip": "apex_habitat.salis.permissions.scoped_has_permission",
    "Transport Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Route Plan": "apex_habitat.salis.permissions.scoped_has_permission",
    "Sponsorship Transfer Case": "apex_habitat.salis.permissions.scoped_has_permission",
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
# Dashboards seed after migrate (when their charts/number cards already exist).
after_migrate = [
    "apex_habitat.habitat.dashboard_seed.seed_all_dashboards",
    "apex_habitat.salis.dashboard_seed.seed_salis_dashboards",
    "apex_habitat.salis.movement_dashboard_seed.seed_movement_dashboards",
]

# Frappe What's New feed — appears in desk notification area, not as a popup
get_changelog_feed = "apex_habitat.habitat.utils.changelog.get_changelog_feed"
