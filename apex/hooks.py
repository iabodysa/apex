# Copyright (c) 2026, AFMCO and contributors
"""Apex hook declarations. Three of these carry a framework fact worth keeping.

``add_to_apps_screen`` is one tile per www/ portal shell. Each admin-style portal points
its ``has_permission`` at a ``has_apps_screen_access()`` sitting beside that page's own
role-set, so the /apps gate cannot drift from the page's real check; driver, masar and
/fleet are ungated by design. The key convention is "apex-" + route slug, and the key is
render-time only (frappe/apps.py:43 returns the installed app name, not this one).

``setup_wizard_complete`` carries TWO completion hooks, as ERPNext splits its own
(erpnext/hooks.py:55-56): the demo build must be a separate step because it only
ENQUEUES, and must not be entangled with the settings the first hook writes.

The ledger DocTypes excluded under ``ignore_links_on_delete``/the deletion-record
declaration are kept out of a Transaction Deletion Record's reach on purpose: it
``frappe.db.delete``s whatever it enumerates
(erpnext/setup/doctype/transaction_deletion_record/transaction_deletion_record.py:393),
which would strand every reversal their ``on_cancel`` posts — the offsetting utility
ledger row, the released rental accrual stamps, the replayed SIM projection. The
mechanism is copied from HRMS's own declaration (hrms/hooks.py:361-371).

``default_log_clearing_doctypes`` lists only non-financial, submittable point-in-time
snapshots; the retention windows cap their growth. ``clear_old_logs`` purges submitted
rows and their child items, so drafts and every financial ledger stay untouched.
"""

from apex.apex_core.setup.workflow_names import (
    WORKFLOW_ACTIONS,
    WORKFLOW_STATES,
    WORKFLOWS,
)

app_name = "apex"
app_title = "Apex"
app_publisher = "AFMCO Support Services Co. Ltd"
app_description = (
    "Apex — workforce operations suite: Habitat (accommodation & facilities), "
    "Salis (movement & fleet), Logistay (client housing services) and Apex Core "
    "(shared kernel)."
)
app_email = "afm@afmcoltd.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext", "hrms"]

add_to_apps_screen = [
    {
        "name": "apex-driver",
        "logo": "/assets/apex/worker_portal/afmco-logo.svg",
        "title": "Driver Portal",
        "route": "/driver",
    },
    {
        "name": "apex-masar",
        "logo": "/assets/apex/worker_portal/icons/masar-icon-192.png",
        "title": "Masar",
        "route": "/masar",
    },
    {
        "name": "apex-masar-supervisor",
        "logo": "/assets/apex/worker_portal/icons/masar-icon-192.png",
        "title": "Masar Supervisor",
        "route": "/masar-supervisor",
        "has_permission": "apex.www.masar_supervisor.has_apps_screen_access",
    },
    {
        "name": "apex-fleet-os",
        "logo": "/assets/apex/worker_portal/afmco-logo.svg",
        "title": "Fleet OS",
        "route": "/fleet-os",
        "has_permission": "apex.www.fleet_os.has_apps_screen_access",
    },
    {
        "name": "apex-fleet",
        "logo": "/assets/apex/worker_portal/afmco-logo.svg",
        "title": "My Fleet",
        "route": "/fleet",
    },
    {
        "name": "apex-housing",
        "logo": "/assets/apex/worker_portal/afmco-logo.svg",
        "title": "Housing",
        "route": "/housing",
        "has_permission": "apex.www.housing.has_apps_screen_access",
    },
    {
        "name": "apex-safety",
        "logo": "/assets/apex/worker_portal/afmco-logo.svg",
        "title": "Safety Rounds",
        "route": "/safety",
        "has_permission": "apex.www.safety.has_apps_screen_access",
    },
]

export_python_type_annotations = True

app_include_js = ["masar_worker_link.bundle.js"]

setup_wizard_requires = "assets/apex/js/apex_setup_wizard.js"
setup_wizard_complete = [
    "apex.apex_core.setup.setup_wizard.setup_wizard_complete",
    "apex.apex_core.setup.demo.setup_demo",
]

extend_bootinfo = ["apex.apex_core.setup.demo.boot_demo"]

company_data_to_be_ignored = [
    "Utility Bill Entry",
    "Rental Settlement",
    "Telecom Contract",
    "SIM Custody Assignment",
]



override_doctype_class = {
    "Notification": "apex.apex_core.overrides.notification.ApexNotification",
}

doc_events = {
    "*": {
        "before_submit": "apex.apex_core.utils.workflow_guard.before_submit",
        "before_cancel": "apex.apex_core.utils.workflow_guard.before_cancel",
    },
    "Report": {
        "validate": "apex.apex_core.utils.report_role_guard.validate",
    },
    "Employee": {
        "on_change": "apex.apex_core.utils.portal_token_security.on_employee_change",
    },
    "Salis Driver": {
        "on_change": "apex.apex_core.utils.portal_token_security.on_salis_driver_change",
    },
    "Address": {
        "validate": "apex.habitat.address_customizations.validate",
    },
    "Site": {},
    "Bed": {},
    "Room": {},
    "QR Location": {
        "before_save": "apex.habitat.doctype.qr_location.qr_location.before_save",
    },
    "Accommodation Ledger": {
        "before_save": "apex.habitat.doctype.accommodation_ledger.accommodation_ledger.before_save",
    },
    "Resident Request": {
        "before_insert": "apex.habitat.doctype.resident_request.resident_request.before_insert",
        "validate": "apex.habitat.doctype.resident_request.resident_request.validate",
        "on_update": "apex.habitat.doctype.resident_request.resident_request.on_update",
    },
    "Building License": {},
    "Camera Access Grant": {},
    "Cleaning Log": {},
    "Audit Remediation Plan": {},
    "Scheduled Task Template": {},
    "Building": {
        "before_save": "apex.habitat.doctype.building.building.before_save",
        "on_update": "apex.habitat.doctype.building.building.on_update",
    },
    "Housing Assignment": {
        "validate": "apex.habitat.doctype.housing_assignment.housing_assignment.validate",
        "on_submit": "apex.habitat.doctype.housing_assignment.housing_assignment.on_submit",
        "on_cancel": "apex.habitat.doctype.housing_assignment.housing_assignment.on_cancel",
    },
    "Housing Checkout": {
        "validate": "apex.habitat.doctype.housing_checkout.housing_checkout.validate",
        "on_submit": "apex.habitat.doctype.housing_checkout.housing_checkout.on_submit",
        "before_cancel": "apex.habitat.doctype.housing_checkout.housing_checkout.before_cancel",
        "on_cancel": "apex.habitat.doctype.housing_checkout.housing_checkout.on_cancel",
    },
    "Lease": {
        "validate": "apex.habitat.doctype.lease.lease.validate",
    },
    "Utility Bill Entry": {
        "validate": "apex.habitat.doctype.utility_bill_entry.utility_bill_entry.validate",
        "on_submit": "apex.habitat.doctype.utility_bill_entry.utility_bill_entry.on_submit",
        "before_cancel": "apex.habitat.doctype.utility_bill_entry.utility_bill_entry.before_cancel",
    },
    "Room Bed Transfer": {
        "validate": "apex.habitat.doctype.room_bed_transfer.room_bed_transfer.validate",
        "on_submit": "apex.habitat.doctype.room_bed_transfer.room_bed_transfer.on_submit",
        "on_cancel": "apex.habitat.doctype.room_bed_transfer.room_bed_transfer.on_cancel",
    },
    "Safety Inspection Report": {},
    "Maintenance Request": {
        "before_save": "apex.habitat.doctype.maintenance_request.maintenance_request.before_save",
    },
    "Custody Article": {},
    "Custody Asset Category": {},
    "Idle Resident Report": {
        "validate": "apex.habitat.doctype.idle_resident_report.idle_resident_report.validate",
        "after_insert": "apex.habitat.doctype.idle_resident_report.idle_resident_report.after_insert",
    },
    "Material Transfer": {
        "validate": "apex.habitat.doctype.material_transfer.material_transfer.validate",
        "on_submit": "apex.habitat.doctype.material_transfer.material_transfer.on_submit",
        "on_cancel": "apex.habitat.doctype.material_transfer.material_transfer.on_cancel",
    },
    "Custody Issue": {
        "validate": "apex.habitat.doctype.custody_issue.custody_issue.validate",
        "on_submit": "apex.habitat.doctype.custody_issue.custody_issue.on_submit",
        "before_cancel": "apex.habitat.doctype.custody_issue.custody_issue.before_cancel",
        "on_cancel": "apex.habitat.doctype.custody_issue.custody_issue.on_cancel",
    },
    "Custody Return": {
        "validate": "apex.habitat.doctype.custody_return.custody_return.validate",
        "on_submit": "apex.habitat.doctype.custody_return.custody_return.on_submit",
        "before_cancel": "apex.habitat.doctype.custody_return.custody_return.before_cancel",
        "on_cancel": "apex.habitat.doctype.custody_return.custody_return.on_cancel",
    },
    "Custody Damage Assessment": {
        "validate": "apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment.validate",
        "on_submit": "apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment.on_submit",
        "before_cancel": "apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment.before_cancel",
    },
    "Operational Depreciation Snapshot": {
        "validate": "apex.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot.validate",
        "before_cancel": "apex.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot.before_cancel",
    },
    "Facility Asset": {},
    "Facility Asset Custody Assignment": {},
    "Facility Asset Movement": {
        "validate": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
        "on_submit": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.on_submit",
        "before_cancel": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.before_cancel",
        "on_cancel": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.on_cancel",
    },
    "Operational Depreciation Policy": {},
    "Subcontractor Service Order": {
        "before_save": "apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order.before_save",
    },
    "Subcontractor Service Contract": {},
    "Utility Account": {},
    "Habitat Settings": {
        "before_save": "apex.apex_core.doctype.habitat_settings.habitat_settings.before_save",
    },
    "Safety Task Catalog": {},
    "Safety Task Execution": {},
    "Maintenance Work Order": {
        "validate": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.validate",
        "on_submit": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.on_submit",
        "before_cancel": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.before_cancel",
    },
    "Scheduled Task Instance": {
        "validate": "apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance.validate",
        "on_submit": "apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance.on_submit",
        "before_cancel": "apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance.before_cancel",
    },
    "Maintenance Inspection Report": {
        "validate": "apex.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report.validate",
        "before_cancel": "apex.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report.before_cancel",
    },
    "Driver Clearance": {
        "on_submit": "apex.apex_core.doctype.masar_worker_token.masar_worker_token.on_driver_clearance_submit",
    },
    "Driver Suspension": {
        "on_submit": "apex.apex_core.utils.portal_token_security.on_driver_suspension_submit",
    },
    "Payment Entry": {
        "on_cancel": "apex.logistay.api.contract_billing.allow_cancel_despite_billing_log",
    },
}

scheduler_events = {
    "daily": [
        "apex.habitat.tasks.cost.daily_accommodation_cost_allocation",
        "apex.habitat.tasks.maintenance.daily_building_license_expiry_check",
        "apex.habitat.tasks.maintenance.open_maintenance_escalation",
        "apex.habitat.tasks.residency.lease_expiry_watchlist",
        "apex.habitat.tasks.residency.idle_resident_aging",
        "apex.habitat.tasks.custody.consumable_custody_expiry_watch",
        "apex.habitat.tasks.scheduled_tasks.daily_scheduled_task_instance_generator",
        "apex.habitat.tasks.occupancy.daily_occupancy_snapshot",
        "apex.habitat.tasks.cleaning.daily_cleaning_log_generator",
        "apex.habitat.tasks.cleaning.auto_create_cleaning_logs",
        "apex.habitat.tasks.safety.daily_safety_task_compliance_scan",
        "apex.habitat.tasks.safety.audit_remediation_deadline_watch",
        "apex.habitat.temporary_worker_engine.link_temporary_workers",
        "apex.salis.tasks.driver.driver_license_expiry_watch",
        "apex.salis.tasks.vehicle.idle_vehicle_watch",
        "apex.salis.tasks.fuel.unreverted_topup_watch",
        "apex.salis.tasks.fuel.overdue_fuel_request_watch",
        "apex.salis.tasks.attendance.missing_attendance_watch",
        "apex.salis.tasks.vehicle.vehicle_compliance_expiry_watch",
        "apex.salis.tasks.workshop.workshop_overstay_watch",
        "apex.salis.tasks.alerts.reconcile_operations_alerts",
        "apex.salis.tasks.alerts.daily_open_alerts_digest",
        "apex.logistay.tasks.sim_alerts.assigned_suspended_or_lost_watch",
        "apex.salis.fuel_engine.accrue_fuel_consumption",
        "apex.salis.rental_engine.daily_rental_accrual",
        "apex.apex_core.utils.workflow_utils.cleanup_orphaned_workflow_actions",
    ],
    "weekly": [
        "apex.habitat.tasks.occupancy.weekly_occupancy_sync",
        "apex.habitat.tasks.custody.weekly_custody_digest",
        "apex.habitat.tasks.safety.weekly_safety_coverage_gate",
        "apex.salis.tasks.vehicle.vehicle_utilization_summary",
        "apex.salis.utilisation_engine.weekly_vehicle_utilisation_snapshot",
    ],
    "monthly": [
        "apex.salis.fuel_engine.monthly_fuel_reconciliation",
        "apex.salis.rental_engine.monthly_rental_reconciliation",
        "apex.apex_core.utils.employee_recovery.monthly_employee_recovery_run",
    ],
    "cron": {
        "*/5 * * * *": [
            "apex.salis.api.boarding_flow.auto_confirm_claimed_boardings",
        ],
        "0 23 * * *": [
            "apex.apex_core.utils.access_log_cleanup.purge_oversized_access_logs",
        ],
    },
}

default_log_clearing_doctypes = {
    "Operations Alert": 90,
    "Occupancy Snapshot": 365,
    "Vehicle Utilisation Snapshot": 365,
    "Operational Depreciation Snapshot": 730,
}

override_doctype_dashboards = {
    "Employee": "apex.habitat.api.employee_links.get_data",
    "Supplier": "apex.habitat.api.supplier_links.get_data",
}

permission_query_conditions = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_query",
    "Housing Assignment": "apex.habitat.permissions.accommodation_assignment_query",
    "Custody Issue": "apex.habitat.permissions.custody_issue_query",
    "Cleaning Log": "apex.habitat.permissions.cleaning_log_query",
    "Building": "apex.habitat.permissions.accommodation_building_query",
    "Safety Round": "apex.habitat.permissions.safety_round_query",
    "Safety Task Execution": "apex.habitat.permissions.safety_task_execution_query",
    "Scheduled Task Instance": "apex.habitat.permissions.scheduled_task_instance_query",
    "Resident Request": "apex.habitat.permissions.accommodation_resident_request_query",
    "Idle Resident Report": "apex.habitat.permissions.idle_resident_report_query",
    "Housing Checkout": "apex.habitat.permissions.housing_checkout_query",
    "Room Bed Transfer": "apex.habitat.permissions.room_bed_transfer_query",
    "Audit Remediation Plan": "apex.habitat.permissions.audit_remediation_plan_query",
    "Vehicle Assignment": "apex.salis.permissions.vehicle_assignment_query",
    "Fuel Request": "apex.salis.permissions.fuel_request_query",
    "Dispatch Trip": "apex.salis.permissions.dispatch_trip_query",
    "Trip Start Log": "apex.salis.permissions.trip_start_log_query",
    "Transport Request": "apex.salis.permissions.transport_request_query",
    "Route Plan": "apex.salis.permissions.route_plan_query",
    "Issue": "apex.salis.permissions.support_ticket_query",
    "Fuel Claim": "apex.salis.permissions.fuel_claim_query",
    "Fuel Quota": "apex.salis.permissions.fuel_quota_query",
    "Fuel Exception Case": "apex.salis.permissions.fuel_exception_case_query",
    "Salis Payment Request": "apex.salis.permissions.salis_payment_request_query",
    "Salis Vehicle": "apex.salis.permissions.salis_vehicle_query",
    "Salis Driver": "apex.salis.permissions.salis_driver_query",
    "Passenger Manifest": "apex.salis.permissions.passenger_manifest_query",
    "Facility Asset Custody Assignment": "apex.habitat.permissions.facility_asset_custody_assignment_query",
    "Operational Depreciation Snapshot": "apex.habitat.permissions.non_financial_depreciation_snapshot_query",
    "Custody Return": "apex.habitat.permissions.custody_return_query",
    "Custody Damage Assessment": "apex.habitat.permissions.custody_damage_assessment_query",
    "Material Transfer": "apex.habitat.permissions.material_transfer_query",
    "Facility Asset Movement": "apex.habitat.permissions.facility_asset_movement_query",
    "Custody Acknowledgment": "apex.habitat.permissions.custody_acknowledgment_query",
    "Custody Handover": "apex.habitat.permissions.custody_handover_query",
    "Facility Asset Delivery": "apex.habitat.permissions.facility_asset_delivery_query",
    "Facility Asset": "apex.habitat.permissions.facility_asset_query",
    "Housing Inventory": "apex.habitat.permissions.housing_inventory_query",
    "Building License": "apex.habitat.permissions.building_license_query",
    "Maintenance Work Order": "apex.habitat.permissions.maintenance_work_order_query",
    "Maintenance Inspection Report": "apex.habitat.permissions.maintenance_inspection_report_query",
    "Occupancy Snapshot": "apex.habitat.permissions.accommodation_occupancy_snapshot_query",
    "Temporary Worker": "apex.habitat.permissions.temporary_worker_query",
    "Arrival Batch": "apex.habitat.permissions.arrival_batch_query",
    "Room": "apex.habitat.permissions.accommodation_room_query",
    "Bed": "apex.habitat.permissions.accommodation_bed_query",
    "Accommodation Stock Ledger": "apex.habitat.permissions.accommodation_stock_ledger_query",
    "Driver Attendance": "apex.salis.permissions.driver_attendance_query",
    "Driver Suspension": "apex.salis.permissions.driver_stop_query",
    "Boarding Scan Log": "apex.salis.permissions.boarding_scan_log_query",
    "Vehicle Damage Write-Off": "apex.salis.permissions.vehicle_damage_write_off_query",
    "Vehicle Incident": "apex.salis.permissions.vehicle_incident_query",
    "Driver Clearance": "apex.salis.permissions.driver_clearance_query",
    "Vehicle Suspension": "apex.salis.permissions.vehicle_stop_query",
    "Movement Cost Transfer": "apex.salis.permissions.movement_cost_transfer_query",
    "Operations Alert": "apex.salis.permissions.operations_alert_query",
    "Telecom Contract": "apex.logistay.permissions.telecom_contract_query",
    "SIM Card": "apex.logistay.permissions.sim_card_query",
    "SIM Custody Assignment": "apex.logistay.permissions.sim_custody_assignment_query",
    "Safety Incident": "apex.habitat.permissions.safety_incident_query",
    "Safety Inspection Report": "apex.habitat.permissions.safety_inspection_report_query",
    "Safety Finding Ledger": "apex.habitat.permissions.safety_finding_ledger_query",
    "Cleaning Compliance Ledger": "apex.habitat.permissions.cleaning_compliance_ledger_query",
}

has_permission = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_has_permission",
    "Housing Assignment": "apex.habitat.permissions.building_scoped_has_permission",
    "Custody Issue": "apex.habitat.permissions.building_scoped_has_permission",
    "Cleaning Log": "apex.habitat.permissions.building_scoped_has_permission",
    "Building": "apex.habitat.permissions.building_scoped_has_permission",
    "Safety Round": "apex.habitat.permissions.building_scoped_has_permission",
    "Safety Task Execution": "apex.habitat.permissions.building_scoped_has_permission",
    "Scheduled Task Instance": "apex.habitat.permissions.building_scoped_has_permission",
    "Resident Request": "apex.habitat.permissions.building_scoped_has_permission",
    "Idle Resident Report": "apex.habitat.permissions.building_scoped_has_permission",
    "Housing Checkout": "apex.habitat.permissions.housing_checkout_has_permission",
    "Audit Remediation Plan": "apex.habitat.permissions.audit_remediation_plan_has_permission",
    "Room Bed Transfer": "apex.habitat.permissions.building_scoped_has_permission",
    "Vehicle Assignment": "apex.salis.permissions.scoped_has_permission",
    "Fuel Request": "apex.salis.permissions.scoped_has_permission",
    "Dispatch Trip": "apex.salis.permissions.dispatch_trip_has_permission",
    "Trip Start Log": "apex.salis.permissions.trip_start_log_has_permission",
    "Transport Request": "apex.salis.permissions.scoped_has_permission",
    "Route Plan": "apex.salis.permissions.scoped_has_permission",
    "Issue": "apex.salis.permissions.scoped_has_permission",
    "Fuel Claim": "apex.salis.permissions.scoped_has_permission",
    "Fuel Quota": "apex.salis.permissions.scoped_has_permission",
    "Fuel Exception Case": "apex.salis.permissions.scoped_has_permission",
    "Salis Payment Request": "apex.salis.permissions.payment_sod_has_permission",
    "Salis Vehicle": "apex.salis.permissions.scoped_has_permission",
    "Salis Driver": "apex.salis.permissions.salis_driver_has_permission",
    "Passenger Manifest": "apex.salis.permissions.scoped_has_permission",
    "Facility Asset Custody Assignment": "apex.habitat.permissions.building_scoped_has_permission",
    "Operational Depreciation Snapshot": "apex.habitat.permissions.building_scoped_has_permission",
    "Custody Return": "apex.habitat.permissions.building_scoped_has_permission",
    "Custody Damage Assessment": "apex.habitat.permissions.building_scoped_has_permission",
    "Custody Acknowledgment": "apex.habitat.permissions.building_scoped_has_permission",
    "Facility Asset": "apex.habitat.permissions.building_scoped_has_permission",
    "Housing Inventory": "apex.habitat.permissions.building_scoped_has_permission",
    "Building License": "apex.habitat.permissions.building_scoped_has_permission",
    "Maintenance Work Order": "apex.habitat.permissions.building_scoped_has_permission",
    "Maintenance Inspection Report": "apex.habitat.permissions.building_scoped_has_permission",
    "Material Transfer": "apex.habitat.permissions.dual_building_scoped_has_permission",
    "Facility Asset Movement": "apex.habitat.permissions.dual_building_scoped_has_permission",
    "Custody Handover": "apex.habitat.permissions.dual_building_scoped_has_permission",
    "Facility Asset Delivery": "apex.habitat.permissions.dual_building_scoped_has_permission",
    "Occupancy Snapshot": "apex.habitat.permissions.building_scoped_has_permission",
    "Temporary Worker": "apex.habitat.permissions.building_scoped_has_permission",
    "Arrival Batch": "apex.habitat.permissions.building_scoped_has_permission",
    "Room": "apex.habitat.permissions.building_scoped_has_permission",
    "Bed": "apex.habitat.permissions.building_scoped_has_permission",
    "Accommodation Stock Ledger": "apex.habitat.permissions.building_scoped_has_permission",
    "Driver Attendance": "apex.salis.permissions.driver_attendance_has_permission",
    "Driver Suspension": "apex.salis.permissions.driver_stop_has_permission",
    "Boarding Scan Log": "apex.salis.permissions.boarding_scan_log_has_permission",
    "Vehicle Damage Write-Off": "apex.salis.permissions.vehicle_damage_write_off_has_permission",
    "Vehicle Incident": "apex.salis.permissions.vehicle_incident_has_permission",
    "Driver Clearance": "apex.salis.permissions.driver_clearance_has_permission",
    "Vehicle Suspension": "apex.salis.permissions.vehicle_stop_has_permission",
    "Movement Cost Transfer": "apex.salis.permissions.movement_cost_transfer_has_permission",
    "Operations Alert": "apex.salis.permissions.operations_alert_has_permission",
    "Telecom Contract": "apex.logistay.permissions.company_scoped_has_permission",
    "SIM Card": "apex.logistay.permissions.company_scoped_has_permission",
    "SIM Custody Assignment": "apex.logistay.permissions.company_scoped_has_permission",
    "Safety Incident": "apex.habitat.permissions.building_scoped_has_permission",
    "Safety Inspection Report": "apex.habitat.permissions.building_scoped_has_permission",
    "Safety Finding Ledger": "apex.habitat.permissions.building_scoped_has_permission",
    "Cleaning Compliance Ledger": "apex.habitat.permissions.building_scoped_has_permission",
}

fixtures = [
    {"dt": "Party Type", "filters": [["name", "in", ["Freelancer"]]]},
    {"dt": "Workflow State", "filters": [["name", "in", list(WORKFLOW_STATES)]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", list(WORKFLOW_ACTIONS)]]},
    {"dt": "Workflow", "filters": [["name", "in", list(WORKFLOWS)]]},
]

after_install = [
    "apex.setup.after_install",
    "apex.salis.setup.after_install",
    "apex.apex_core.setup.seed.seed_all",
    "apex.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    "apex.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    "apex.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
    "apex.apex_core.setup.seeders.habitat_core_link_perms_seed.seed_habitat_core_link_perms",
    "apex.apex_core.setup.seeders.module_profile_seed.seed_module_profiles",
    "apex.patches.v1_x.reorder_root_workspace_creation.execute",
]

after_sync = []
after_migrate = [
    "apex.setup.after_migrate",
    "apex.apex_core.setup.seed.seed_all",
    "apex.apex_core.setup.seeders.habitat_auto_email_reports_seed.seed_auto_email_reports",
    "apex.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    "apex.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    "apex.apex_core.setup.seeders.salis_issue_seed.seed_salis_issue_masters",
    "apex.apex_core.setup.seeders.habitat_core_link_perms_seed.seed_habitat_core_link_perms",
    "apex.apex_core.setup.seeders.module_profile_seed.seed_module_profiles",
    "apex.patches.v1_0.seed_salis_settings.execute",
    "apex.setup.create_roles",
    "apex.setup.create_role_profiles",
    "apex.patches.v1_x.reorder_root_workspace_creation.execute",
]

get_changelog_feed = "apex.apex_core.utils.changelog.get_changelog_feed"
