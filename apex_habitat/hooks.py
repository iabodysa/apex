# [#b4hlng]
# [#6tfpa4]
# [#92qnpg]
app_name = "apex_habitat"
app_title = "Apex"
app_publisher = "AFMCO Support Services Co. Ltd"
app_description = "Apex — workforce operations suite: Habitat (accommodation & facilities) and Salis (movement & fleet)."
app_email = "afm@afmcoltd.com"
app_license = "MIT"

# [#kk7yf0]
required_apps = ["frappe", "erpnext", "hrms"]

# [#9m1nu9]
export_python_type_annotations = True

# [#abcrib]
# [#c9z8l6]
app_include_js = ["masar_worker_link.bundle.js"]

# [#mljwym]
# [#gx5ils]
# [#qu7skh]
# [#muhku4]
# [#t61jgv]
setup_wizard_requires = "assets/apex_habitat/js/apex_setup_wizard.js"
setup_wizard_complete = "apex_habitat.apex_core.setup.setup_wizard.setup_wizard_complete"


# [#pjyorr]

# [#j0knn7]
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
    # [#k4s7wl]
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
    # [#fc2p7q]
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
    # [#9rv3zv]
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

# [#hsa89r]
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
        # [#gvuy90]
        # [#pcj3xk]
        "apex_habitat.habitat.temporary_worker_engine.link_temporary_workers",
        # [#p5yxar]
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
        # [#5ov0x2]
        # [#em9ytk]
        # [#syq0vg]
        "apex_habitat.apex_core.utils.workflow_utils.cleanup_orphaned_workflow_actions",
    ],
    "weekly": [
        "apex_habitat.habitat.tasks.weekly_occupancy_sync",
        "apex_habitat.habitat.tasks.weekly_safety_task_compliance_scan",
        "apex_habitat.salis.tasks.vehicle_utilization_summary",
        "apex_habitat.salis.utilisation_engine.weekly_vehicle_utilisation_snapshot",
    ],
    "monthly": [
        "apex_habitat.salis.fuel_engine.monthly_fuel_reconciliation",
        # [#k5fyzy]
        # [#bx90uq]
        # [#jsmo1j]
        "apex_habitat.salis.rental_engine.monthly_rental_reconciliation",
    ],
}

# [#pgcxia]
# [#mlxnu7]
# [#4wg5xx]
# [#em3yq2]
# [#mghecf]
default_log_clearing_doctypes = {
    "Operations Alert": 90,
    "Accommodation Occupancy Snapshot": 365,
    "Vehicle Utilisation Snapshot": 365,
    # [#p89hok]
    # [#ttlw7k]
    # [#hhh2cg]
    "Non-Financial Depreciation Snapshot": 730,
}

# [#9cgm64]
override_doctype_dashboards = {
    "Employee": "apex_habitat.habitat.api.employee_links.get_data",
    "Supplier": "apex_habitat.habitat.api.supplier_links.get_data",
}

# [#eshwew]
# [#bw7k33]
# [#ijx3j8]
# [#tgdflb]
# [#5ewfhq]
permission_query_conditions = {
    "Maintenance Request": "apex_habitat.habitat.permissions.maintenance_request_query",
    # [#rkupl9]
    "Accommodation Assignment": "apex_habitat.habitat.permissions.accommodation_assignment_query",
    "Custody Issue": "apex_habitat.habitat.permissions.custody_issue_query",
    "Cleaning Log": "apex_habitat.habitat.permissions.cleaning_log_query",
    "Accommodation Building": "apex_habitat.habitat.permissions.accommodation_building_query",
    "Vehicle Assignment": "apex_habitat.salis.permissions.vehicle_assignment_query",
    "Fuel Request": "apex_habitat.salis.permissions.fuel_request_query",
    "Dispatch Trip": "apex_habitat.salis.permissions.dispatch_trip_query",
    "Trip Start Log": "apex_habitat.salis.permissions.trip_start_log_query",
    "Transport Request": "apex_habitat.salis.permissions.transport_request_query",
    "Route Plan": "apex_habitat.salis.permissions.route_plan_query",
    # [#r3p52p]
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
    # [#hwtm5f]
    # [#3eiuqj]
    # [#bbzqdw]
    "Maintenance Request": "apex_habitat.habitat.permissions.maintenance_request_has_permission",
    # [#6mspex]
    "Accommodation Assignment": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Custody Issue": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Cleaning Log": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Accommodation Building": "apex_habitat.habitat.permissions.building_scoped_has_permission",
    "Vehicle Assignment": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Dispatch Trip": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#gsmiph]
    # [#og0l6z]
    # [#2x69y0]
    # [#phomll]
    "Trip Start Log": "apex_habitat.salis.permissions.trip_start_log_has_permission",
    "Transport Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Route Plan": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#r3p52p]
    "Issue": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Claim": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Quota": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Exception Case": "apex_habitat.salis.permissions.scoped_has_permission",
    "Salis Payment Request": "apex_habitat.salis.permissions.payment_sod_has_permission",
    "Salis Vehicle": "apex_habitat.salis.permissions.scoped_has_permission",
    # [#11cgi1]
    # [#eyx9hh]
    # [#18sr1a]
    # [#b1ux9z]
    # [#4cjem3]
    # [#h64xj0]
    "Salis Driver": "apex_habitat.salis.permissions.salis_driver_has_permission",
    "Passenger Manifest": "apex_habitat.salis.permissions.scoped_has_permission",
}

# [#j2jahj]
# [#od1fgp]
# [#mh56eb]
# [#lq5jvw]
# [#af8wb0]
# [#jd7vy0]
# [#35i126]
fixtures = [
    # [#4gnzjj]
    # [#e8ce9w]
    # [#sz995o]
    # [#g5fgnw]
    # [#veb6ya]
    {"dt": "Role", "filters": [["name", "in", ["Accommodation Manager", "Resident Supervisor", "Finance Manager", "Internal Auditor"]]]},
    # [#r96a4x]
    {"dt": "Role", "filters": [["name", "in", ["Maintenance Technician", "Cleaning Supervisor", "Safety Officer", "Resident Request Coordinator"]]]},
    # [#520way]
    # [#7bt0pe]
    # [#jsfs5k]
    # [#gev0bm]
    # [#gdsy32]
    # [#pabj7t]
    # [#tggw3r]
    # [#kfmohf]
    # [#tbejsi]
    # [#1ugzrc]
    # [#gtjbvc]
    # [#sdjg7g]
    # [#au3kly]
    # [#k35fwa]
    # [#7m6xo8]
    # [#b7n1ld]
    # [#ahi4wp]
    # [#gk151m]
    # [#hz6fs5]
    # [#q0og0m]
    {"dt": "Role", "filters": [["name", "in", ["Fleet Project Manager", "Fleet Supervisor", "Government Relations Officer"]]]},
    # [#d4kytf]
    # [#6v4nh9]
    # [#qk5d97]
    # [#2d2duu]
    # [#4ag5qx]
    # [#rq1lnx]
]

# [#sqws11]
after_install = [
    "apex_habitat.setup.after_install",
    "apex_habitat.salis.setup.after_install",
    # [#4igo0x]
    # [#1ana8n]
    # [#n9cbmp]
    # [#8fz94p]
    # [#9h5e6a]
    # [#ajcv1c]
    "apex_habitat.apex_core.setup.seed.seed_all",
    # [#oja7bv]
    # [#sdx5lt]
    # [#6nmzbi]
    # [#o9ve9s]
    # [#43lh6e]
    # [#pz09u4]
    # [#rb30tj]
    # [#ewfnmb]
    # [#8mlxun]
    "apex_habitat.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    # [#oy8lk9]
    # [#q9ipfy]
    # [#20vkro]
    "apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    # [#9sa483]
    # [#hkvjbo]
    # [#3o2g6u]
    # [#osm7a2]
    "apex_habitat.apex_core.setup.seeders.salis_workflow_seed.seed_salis_workflows",
    # [#cfecy2]
    # [#iilmc6]
    # [#d5c5v1]
    "apex_habitat.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
]

# [#j55yx5]
# [#jreze8]
# [#azlvia]
# [#l59eg6]
# [#ak6ti5]
# [#qzphva]
# [#oxcf2t]
after_sync = []
# [#ba50gn]
# [#l6tdg4]
after_migrate = [
    # [#anrsy5]
    # [#2xd768]
    # [#9n0j29]
    "apex_habitat.apex_core.setup.seed.seed_all",
    # [#t2h62w]
    # [#jbc6xu]
    # [#7sclsj]
    # [#t0ctoo]
    # [#qivocy]
    # [#8afvl8]
    # [#t99gij]
    "apex_habitat.apex_core.setup.seeders.habitat_auto_email_reports_seed.seed_auto_email_reports",
    # [#aiw32l]
    # [#os4xpa]
    # [#43lh6e]
    # [#gqvbgy]
    # [#9jbxb8]
    "apex_habitat.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    # [#fv8m5a]
    # [#hfitcu]
    "apex_habitat.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    # [#svrpde]
    # [#h4igl2]
    # [#4g9zu3]
    "apex_habitat.apex_core.setup.seeders.salis_workflow_seed.seed_salis_workflows",
    # [#4o7457]
    # [#din3u8]
    # [#4w3tkh]
    "apex_habitat.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
    # [#4casx8]
    # [#mty2qp]
    # [#77175v]
    # [#4lhwow]
    "apex_habitat.patches.v1_0.seed_salis_settings.execute",
    # [#1kg78y]
    # [#9jp1cl]
    # [#ojghh5]
    # [#odxznc]
    # [#ak34qe]
    # [#plmz05]
    # [#rjgpff]
    "apex_habitat.setup.create_roles",
    "apex_habitat.setup.create_role_profiles",
]

# [#88aspj]
# [#ai14rs]
# [#8fxciq]
# [#is2g6c]
before_tests = "apex_habitat.tests.before_tests.before_tests"

# [#p8ikte]
get_changelog_feed = "apex_habitat.apex_core.utils.changelog.get_changelog_feed"
