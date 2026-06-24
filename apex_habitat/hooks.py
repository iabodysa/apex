# [#dvwfff]
app_name = "apex_habitat"
app_title = "Apex"
app_publisher = "AFMCO Support Services Co. Ltd"
app_description = "Apex — workforce operations suite: Habitat (accommodation & facilities) and Salis (movement & fleet)."
app_email = "afm@afmcoltd.com"
app_license = "MIT"

# [#4d5ed9]
required_apps = ["frappe", "erpnext", "hrms"]

# [#3n2bsa]
export_python_type_annotations = True

# [#9molmh]
app_include_js = ["masar_worker_link.bundle.js"]

# [#dfjden]
setup_wizard_requires = "assets/apex_habitat/js/apex_setup_wizard.js"
setup_wizard_complete = "apex_habitat.apex_core.setup.setup_wizard.setup_wizard_complete"


# [#nc1irs]

# [#34xywz]
doc_events = {
    "Accommodation Site": {},
    "Accommodation Bed": {},
    "Accommodation Room": {},
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
    "Building License": {},
    "Camera Access Grant": {},
    "Cleaning Log": {},
    "Client Audit Remediation Plan": {},
    "Scheduled Task Template": {},
    "Accommodation Building": {
        "before_save": "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.before_save",
        "on_update": "apex_habitat.habitat.doctype.accommodation_building.accommodation_building.on_update",
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
    "Safety Inspection Report": {},
    "Maintenance Request": {
        "before_save": "apex_habitat.habitat.doctype.maintenance_request.maintenance_request.before_save",
    },
    "Custody Article": {},
    "Custody Asset Category": {},
    # [#ojl68r]
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
    # [#i91sa1]
    "Facility Asset": {},
    "Facility Asset Custody Assignment": {},
    "Facility Asset Movement": {
        "validate": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
        "on_submit": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.before_cancel",
        "on_cancel": "apex_habitat.habitat.doctype.facility_asset_movement.facility_asset_movement.on_cancel",
    },
    "Operational Depreciation Policy": {},
    "Subcontractor Service Order": {
        "before_save": "apex_habitat.habitat.doctype.subcontractor_service_order.subcontractor_service_order.before_save",
    },
    "Subcontractor Service Contract": {},
    "Utility Account": {},
    "Habitat Settings": {
        "before_save": "apex_habitat.apex_core.doctype.habitat_settings.habitat_settings.before_save",
    },
    "Safety Task Catalog": {},
    "Safety Task Execution": {},
    "Maintenance Work Order": {
        "validate": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.validate",
        "on_submit": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.on_submit",
        "before_cancel": "apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order.before_cancel",
    },
    # [#rt1blm]
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

# [#qjzdot]
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
        # [#wave3-safety]
        "apex_habitat.habitat.tasks.daily_safety_task_compliance_scan",
        "apex_habitat.habitat.tasks.audit_remediation_deadline_watch",
        # [#8d555o]
        "apex_habitat.habitat.temporary_worker_engine.link_temporary_workers",
        # [#3mjdri]
        "apex_habitat.salis.tasks.driver_license_expiry_watch",
        "apex_habitat.salis.tasks.idle_vehicle_watch",
        "apex_habitat.salis.tasks.unreverted_topup_watch",
        "apex_habitat.salis.tasks.overdue_fuel_request_watch",
        "apex_habitat.salis.tasks.missing_attendance_watch",
        "apex_habitat.salis.tasks.vehicle_compliance_expiry_watch",
        "apex_habitat.salis.tasks.workshop_overstay_watch",
        "apex_habitat.salis.tasks.reconcile_operations_alerts",
        "apex_habitat.salis.fuel_engine.accrue_fuel_consumption",
        "apex_habitat.salis.rental_engine.daily_rental_accrual",
        # [#ptjnq1]
        "apex_habitat.apex_core.utils.workflow_utils.cleanup_orphaned_workflow_actions",
    ],
    "weekly": [
        "apex_habitat.habitat.tasks.weekly_occupancy_sync",
        # [#wave3-safety]
        "apex_habitat.habitat.tasks.weekly_safety_coverage_gate",
        "apex_habitat.salis.tasks.vehicle_utilization_summary",
        "apex_habitat.salis.utilisation_engine.weekly_vehicle_utilisation_snapshot",
    ],
    "monthly": [
        "apex_habitat.salis.fuel_engine.monthly_fuel_reconciliation",
        # [#payd2f]
        "apex_habitat.salis.rental_engine.monthly_rental_reconciliation",
    ],
}

# [#ow8j67]
default_log_clearing_doctypes = {
    "Operations Alert": 90,
    "Accommodation Occupancy Snapshot": 365,
    "Vehicle Utilisation Snapshot": 365,
    # [#263f83]
    "Non-Financial Depreciation Snapshot": 730,
}

# [#4z2uut]
override_doctype_dashboards = {
    "Employee": "apex_habitat.habitat.api.employee_links.get_data",
    "Supplier": "apex_habitat.habitat.api.supplier_links.get_data",
}

# [#2pnntm]
permission_query_conditions = {
    "Maintenance Request": "apex_habitat.habitat.permissions.maintenance_request_query",
    # [#8oiixt]
    "Accommodation Assignment": "apex_habitat.habitat.permissions.accommodation_assignment_query",
    "Custody Issue": "apex_habitat.habitat.permissions.custody_issue_query",
    "Cleaning Log": "apex_habitat.habitat.permissions.cleaning_log_query",
    "Accommodation Building": "apex_habitat.habitat.permissions.accommodation_building_query",
    # [#wave4-safety]
    "Safety Round": "apex_habitat.habitat.permissions.safety_round_query",
    "Safety Task Execution": "apex_habitat.habitat.permissions.safety_task_execution_query",
    "Scheduled Task Instance": "apex_habitat.habitat.permissions.scheduled_task_instance_query",
    "Vehicle Assignment": "apex_habitat.salis.permissions.vehicle_assignment_query",
    "Fuel Request": "apex_habitat.salis.permissions.fuel_request_query",
    "Dispatch Trip": "apex_habitat.salis.permissions.dispatch_trip_query",
    "Trip Start Log": "apex_habitat.salis.permissions.trip_start_log_query",
    "Transport Request": "apex_habitat.salis.permissions.transport_request_query",
    "Route Plan": "apex_habitat.salis.permissions.route_plan_query",
    # [#pq1o3p]
    "Issue": "apex_habitat.salis.permissions.support_ticket_query",
    "Fuel Claim": "apex_habitat.salis.permissions.fuel_claim_query",
    "Fuel Quota": "apex_habitat.salis.permissions.fuel_quota_query",
    "Fuel Exception Case": "apex_habitat.salis.permissions.fuel_exception_case_query",
    "Salis Payment Request": "apex_habitat.salis.permissions.salis_payment_request_query",
    "Salis Vehicle": "apex_habitat.salis.permissions.salis_vehicle_query",
    "Salis Driver": "apex_habitat.salis.permissions.salis_driver_query",
    "Passenger Manifest": "apex_habitat.salis.permissions.passenger_manifest_query",
}

has_permission = {
    # [#jgdlwi]
    "Maintenance Request": "apex_habitat.habitat.permissions.maintenance_request_has_permission",
    # [#s6j0i9]
    "Accommodation Assignment": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Custody Issue": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Cleaning Log": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Accommodation Building": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    # [#wave4-safety]
    "Safety Round": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Safety Task Execution": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Scheduled Task Instance": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Vehicle Assignment": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Dispatch Trip": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#s72nfj]
    "Trip Start Log": "apex_habitat.salis.permissions.trip_start_log_has_permission",
    "Transport Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Route Plan": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#pq1o3p]
    "Issue": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Claim": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Quota": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Exception Case": "apex_habitat.salis.permissions.scoped_has_permission",
    "Salis Payment Request": "apex_habitat.salis.permissions.payment_sod_has_permission",
    "Salis Vehicle": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#1v1380]
    "Salis Driver": "apex_habitat.salis.permissions.salis_driver_has_permission",
    "Passenger Manifest": "apex_habitat.salis.permissions.scoped_has_permission",
}

# [#eo76cf]
fixtures = [
    # [#qzi031]
    {"dt": "Role", "filters": [["name", "in", ["Accommodation Manager", "Resident Supervisor", "Finance Manager", "Internal Auditor"]]]},
    # [#r86uty]
    {"dt": "Role", "filters": [["name", "in", ["Maintenance Technician", "Cleaning Supervisor", "Safety Officer", "Resident Request Coordinator"]]]},
    # [#e3f5ip]
    {"dt": "Role", "filters": [["name", "in", ["Fleet Project Manager", "Fleet Supervisor", "Government Relations Officer"]]]},
    # [#40ogr7]
    # Item Group is a NestedSet — seeded via patch (seed_accommodation_item_groups),
    # not fixtures, since a fixture import crashes on a fresh site's NULL-lft/rgt root.
    # [#t543it] Worker-housing procurement catalog for the Items shopping surface.
    {"dt": "Item", "filters": [["item_code", "like", "ACC-%"]]},
]

# [#6mioka]
after_install = [
    "apex_habitat.setup.after_install",
    "apex_habitat.salis.setup.after_install",
    # [#imj0oa]
    "apex_habitat.apex_core.setup.seed.seed_all",
    # [#kn80cn]
    "apex_habitat.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    # [#917n9u]
    "apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    # [#zy072c]
    "apex_habitat.apex_core.setup.seeders.salis_workflow_seed.seed_salis_workflows",
    # [#2oqhfm]
    "apex_habitat.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
]

# [#6xge34]
after_sync = []
# [#dczcal]
after_migrate = [
    # [#2k7wg7]
    "apex_habitat.apex_core.setup.seed.seed_all",
    # [#gmne6k]
    "apex_habitat.apex_core.setup.seeders.habitat_auto_email_reports_seed.seed_auto_email_reports",
    # [#5lhe9n]
    "apex_habitat.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    # [#puz3yc]
    "apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    # [#mv2xth]
    "apex_habitat.apex_core.setup.seeders.salis_workflow_seed.seed_salis_workflows",
    # [#tk37r7]
    "apex_habitat.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
    # [#hi9721]
    "apex_habitat.patches.v1_0.seed_salis_settings.execute",
    # [#byftwb]
    "apex_habitat.setup.create_roles",
    "apex_habitat.setup.create_role_profiles",
]

# [#10mrjh]
before_tests = "apex_habitat.tests.before_tests.before_tests"

# [#susk3d]
get_changelog_feed = "apex_habitat.apex_core.utils.changelog.get_changelog_feed"
