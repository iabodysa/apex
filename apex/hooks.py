# Copyright (c) 2026, afmcoltd
"""Apex hook declarations. Three of these carry a framework fact worth keeping.

``default_log_clearing_doctypes`` lists only non-financial, submittable point-in-time
snapshots; the retention windows cap their growth. ``clear_old_logs`` purges submitted
rows and their child items, so drafts and every financial ledger stay untouched.
"""

from apex.apex_core.setup.support_names import (
    ISSUE_PRIORITIES,
    ISSUE_TYPES,
)
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
        "name": "apex",
        "logo": "/assets/apex/images/apex-app-icon.svg",
        "title": "Apex",
        "route": "/app/apex",
        "has_permission": "apex.check_app_permission",
    },
    {
        "name": "apex-driver",
        "logo": "/assets/apex/images/masar-app-icon.svg",
        "title": "Driver",
        "route": "/driver",
    },
    {
        "name": "apex-masar",
        "logo": "/assets/apex/images/masar-app-icon.svg",
        "title": "Masar",
        "route": "/masar",
    },
    {
        "name": "apex-masar-supervisor",
        "logo": "/assets/apex/images/masar-app-icon.svg",
        "title": "Masar Supervisor",
        "route": "/masar-supervisor",
        "has_permission": "apex.www.masar_supervisor.has_apps_screen_access",
    },
    {
        "name": "apex-fleet-os",
        "logo": "/assets/apex/images/salis-app-icon.svg",
        "title": "Fleet Operations",
        "route": "/fleet-os",
        "has_permission": "apex.www.fleet_os.has_apps_screen_access",
    },
    {
        "name": "apex-fleet",
        "logo": "/assets/apex/images/salis-app-icon.svg",
        "title": "My Fleet",
        "route": "/fleet",
    },
    {
        "name": "apex-housing",
        "logo": "/assets/apex/images/apex-secondary-icon.svg",
        "title": "Housing",
        "route": "/housing",
        "has_permission": "apex.www.housing.has_apps_screen_access",
    },
    {
        "name": "apex-safety",
        "logo": "/assets/apex/images/apex-secondary-icon.svg",
        "title": "Safety Rounds",
        "route": "/safety",
        "has_permission": "apex.www.safety.has_apps_screen_access",
    },
]

export_python_type_annotations = True

before_tests = "apex.tests.bootstrap.before_tests"

app_include_js = [
    "masar_worker_link.bundle.js",
    "habitat_desk.bundle.js",
    "apex_desk.bundle.js",
    "apex_report_filters.bundle.js",
]
app_include_css = ["habitat_desk.bundle.css"]
web_include_js = ["/assets/apex/js/apex_web_form.js"]

after_request = [
    "apex.apex_core.utils.portal_response_headers.apply_portal_response_headers"
]

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
    "Issue Priority": {
        "on_trash": "apex.apex_core.setup.salis_support.refuse_shipped_issue_priority_deletion",
    },
    "Issue Type": {
        "on_trash": "apex.apex_core.setup.salis_support.refuse_shipped_issue_type_deletion",
        "before_rename": "apex.apex_core.setup.salis_support.refuse_shipped_issue_type_edit",
        "validate": "apex.apex_core.setup.salis_support.refuse_shipped_issue_type_edit",
    },
    "Workflow": {
        "validate": "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit",
        "before_rename": "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit",
        "on_trash": "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit",
    },
    "Workflow Document State": {
        "validate": "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit",
    },
    "Workflow Transition": {
        "validate": "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit",
    },
    "Employee": {
        "on_change": "apex.apex_core.utils.portal_identity.on_employee_change",
    },
    "Additional Salary": {
        "before_submit": "apex.apex_core.utils.employee_recovery.validate_recovery_additional_salary",
    },
    "Salary Slip": {
        "validate": "apex.apex_core.utils.employee_loan_recovery.cap_loan_installments_to_current_pay",
    },
    "Salis Driver": {
        "on_change": "apex.apex_core.utils.portal_identity.on_salis_driver_change",
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
        "validate": "apex.habitat.doctype.maintenance_request.maintenance_request.validate",
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
        "on_submit": "apex.apex_core.utils.portal_identity.on_driver_suspension_submit",
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
        "apex.habitat.tasks.safety.daily_safety_task_compliance_scan",
        "apex.habitat.tasks.safety.audit_remediation_deadline_watch",
        "apex.habitat.temporary_worker_engine.link_temporary_workers",
        "apex.salis.tasks.vehicle.idle_vehicle_watch",
        "apex.salis.tasks.fuel.unreverted_topup_watch",
        "apex.salis.tasks.attendance.missing_attendance_watch",
        "apex.salis.tasks.vehicle.vehicle_compliance_expiry_watch",
        "apex.salis.tasks.workshop.workshop_overstay_watch",
        "apex.salis.tasks.alerts.reconcile_operations_alerts",
        "apex.salis.tasks.dispatch.daily_dispatch_trip_generation",
        "apex.logistay.tasks.sim_alerts.assigned_suspended_or_lost_watch",
        "apex.logistay.tasks.contract_alerts.contract_expiry_watch",
        "apex.logistay.tasks.contract_alerts.contract_expiry_soon_watch",
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
        "0 23 * * *": [
            "apex.apex_core.utils.access_log_cleanup.purge_oversized_access_logs",
        ],
    },
}

default_log_clearing_doctypes = {
    "Occupancy Snapshot": 365,
    "Vehicle Utilisation Snapshot": 365,
    "Operational Depreciation Snapshot": 730,
    "Access Log": 90,
}

override_doctype_dashboards = {
    "Employee": "apex.habitat.api.employee_links.get_data",
    "Supplier": "apex.habitat.api.supplier_links.get_data",
}

_HABITAT_SCOPE_QUERY = "apex.habitat.permissions.building_scope_query"
_HABITAT_NO_BUILDING_QUERY = "apex.habitat.permissions.refuse_a_supervisor_with_no_building"
_SALIS_SCOPE_QUERY = "apex.salis.permissions.project_scope_query"
_LOGISTAY_SCOPE_QUERY = "apex.logistay.permissions.company_scope_query"

_HABITAT_SCOPE_CHECK = "apex.habitat.permissions.building_scoped_has_permission"
_SALIS_SCOPE_CHECK = "apex.salis.permissions.project_scoped_has_permission"
_LOGISTAY_SCOPE_CHECK = "apex.logistay.permissions.company_scoped_has_permission"

permission_query_conditions = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_query",
    "Housing Assignment": _HABITAT_NO_BUILDING_QUERY,
    "Custody Issue": _HABITAT_NO_BUILDING_QUERY,
    "Cleaning Log": _HABITAT_NO_BUILDING_QUERY,
    "Building": _HABITAT_NO_BUILDING_QUERY,
    "Safety Round": _HABITAT_NO_BUILDING_QUERY,
    "Safety Task Execution": _HABITAT_NO_BUILDING_QUERY,
    "Scheduled Task Instance": _HABITAT_NO_BUILDING_QUERY,
    "Resident Request": _HABITAT_NO_BUILDING_QUERY,
    "Idle Resident Report": _HABITAT_NO_BUILDING_QUERY,
    "Housing Checkout": _HABITAT_SCOPE_QUERY,
    "Room Bed Transfer": _HABITAT_SCOPE_QUERY,
    "Audit Remediation Plan": _HABITAT_SCOPE_QUERY,
    "Vehicle Assignment": _SALIS_SCOPE_QUERY,
    "Fuel Request": _SALIS_SCOPE_QUERY,
    "Dispatch Trip": _SALIS_SCOPE_QUERY,
    "Trip Start Log": _SALIS_SCOPE_QUERY,
    "Transport Request": _SALIS_SCOPE_QUERY,
    "Route Assignment": _SALIS_SCOPE_QUERY,
    "Route Plan": _SALIS_SCOPE_QUERY,
    "Issue": _SALIS_SCOPE_QUERY,
    "Fuel Claim": _SALIS_SCOPE_QUERY,
    "Fuel Quota": _SALIS_SCOPE_QUERY,
    "Fuel Exception Case": _SALIS_SCOPE_QUERY,
    "Salis Payment Request": _SALIS_SCOPE_QUERY,
    "Salis Vehicle": _SALIS_SCOPE_QUERY,
    "Salis Driver": _SALIS_SCOPE_QUERY,
    "Passenger Manifest": _SALIS_SCOPE_QUERY,
    "Masar Worker Token": "apex.apex_core.utils.portal_identity.masar_worker_token_scope_query",
    "Facility Asset Custody Assignment": _HABITAT_NO_BUILDING_QUERY,
    "Operational Depreciation Snapshot": _HABITAT_NO_BUILDING_QUERY,
    "Custody Return": _HABITAT_NO_BUILDING_QUERY,
    "Custody Damage Assessment": _HABITAT_NO_BUILDING_QUERY,
    "Material Transfer": _HABITAT_SCOPE_QUERY,
    "Facility Asset Movement": _HABITAT_SCOPE_QUERY,
    "Custody Acknowledgment": _HABITAT_NO_BUILDING_QUERY,
    "Custody Handover": _HABITAT_SCOPE_QUERY,
    "Facility Asset Delivery": _HABITAT_SCOPE_QUERY,
    "Facility Asset": _HABITAT_NO_BUILDING_QUERY,
    "Housing Inventory": _HABITAT_NO_BUILDING_QUERY,
    "Building License": _HABITAT_NO_BUILDING_QUERY,
    "Maintenance Work Order": _HABITAT_NO_BUILDING_QUERY,
    "Maintenance Inspection Report": _HABITAT_NO_BUILDING_QUERY,
    "Occupancy Snapshot": _HABITAT_NO_BUILDING_QUERY,
    "Temporary Worker": _HABITAT_NO_BUILDING_QUERY,
    "Arrival Batch": _HABITAT_NO_BUILDING_QUERY,
    "Room": _HABITAT_NO_BUILDING_QUERY,
    "Bed": _HABITAT_NO_BUILDING_QUERY,
    "Accommodation Stock Ledger": _HABITAT_NO_BUILDING_QUERY,
    "Driver Attendance": _SALIS_SCOPE_QUERY,
    "Driver Suspension": _SALIS_SCOPE_QUERY,
    "Boarding Scan Log": _SALIS_SCOPE_QUERY,
    "Vehicle Damage Write-Off": _SALIS_SCOPE_QUERY,
    "Vehicle Incident": _SALIS_SCOPE_QUERY,
    "Driver Clearance": _SALIS_SCOPE_QUERY,
    "Vehicle Suspension": _SALIS_SCOPE_QUERY,
    "Movement Cost Transfer": _SALIS_SCOPE_QUERY,
    "Vehicle Handover": _SALIS_SCOPE_QUERY,
    "Wash Request": _SALIS_SCOPE_QUERY,
    "Fuel Daily Log": _SALIS_SCOPE_QUERY,
    "Rental Vehicle Movement": _SALIS_SCOPE_QUERY,
    "Movement Cost Recovery": _SALIS_SCOPE_QUERY,
    "Transport Trip Rating": _SALIS_SCOPE_QUERY,
    "Telecom Contract": _LOGISTAY_SCOPE_QUERY,
    "SIM Card": _LOGISTAY_SCOPE_QUERY,
    "SIM Custody Assignment": _LOGISTAY_SCOPE_QUERY,
    "Safety Incident": _HABITAT_NO_BUILDING_QUERY,
    "Safety Inspection Report": _HABITAT_NO_BUILDING_QUERY,
    "Safety Finding Ledger": _HABITAT_NO_BUILDING_QUERY,
    "Cleaning Compliance Ledger": _HABITAT_NO_BUILDING_QUERY,
}

has_permission = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_has_permission",
    "Housing Assignment": _HABITAT_SCOPE_CHECK,
    "Custody Issue": _HABITAT_SCOPE_CHECK,
    "Cleaning Log": _HABITAT_SCOPE_CHECK,
    "Building": _HABITAT_SCOPE_CHECK,
    "Safety Round": _HABITAT_SCOPE_CHECK,
    "Safety Task Execution": _HABITAT_SCOPE_CHECK,
    "Scheduled Task Instance": _HABITAT_SCOPE_CHECK,
    "Resident Request": _HABITAT_SCOPE_CHECK,
    "Idle Resident Report": _HABITAT_SCOPE_CHECK,
    "Housing Checkout": _HABITAT_SCOPE_CHECK,
    "Audit Remediation Plan": _HABITAT_SCOPE_CHECK,
    "Room Bed Transfer": _HABITAT_SCOPE_CHECK,
    "Vehicle Assignment": _SALIS_SCOPE_CHECK,
    "Fuel Request": _SALIS_SCOPE_CHECK,
    "Dispatch Trip": _SALIS_SCOPE_CHECK,
    "Trip Start Log": _SALIS_SCOPE_CHECK,
    "Transport Request": _SALIS_SCOPE_CHECK,
    "Route Assignment": _SALIS_SCOPE_CHECK,
    "Route Plan": _SALIS_SCOPE_CHECK,
    "Issue": _SALIS_SCOPE_CHECK,
    "Fuel Claim": _SALIS_SCOPE_CHECK,
    "Fuel Quota": _SALIS_SCOPE_CHECK,
    "Fuel Exception Case": _SALIS_SCOPE_CHECK,
    "Salis Payment Request": _SALIS_SCOPE_CHECK,
    "Salis Vehicle": _SALIS_SCOPE_CHECK,
    "Salis Driver": _SALIS_SCOPE_CHECK,
    "Passenger Manifest": _SALIS_SCOPE_CHECK,
    "Masar Worker Token": "apex.apex_core.utils.portal_identity.masar_worker_token_has_permission",
    "Portal Push Subscription": "apex.apex_core.utils.portal_identity.portal_push_subscription_has_permission",
    "Facility Asset Custody Assignment": _HABITAT_SCOPE_CHECK,
    "Operational Depreciation Snapshot": _HABITAT_SCOPE_CHECK,
    "Custody Return": _HABITAT_SCOPE_CHECK,
    "Custody Damage Assessment": _HABITAT_SCOPE_CHECK,
    "Custody Acknowledgment": _HABITAT_SCOPE_CHECK,
    "Facility Asset": _HABITAT_SCOPE_CHECK,
    "Housing Inventory": _HABITAT_SCOPE_CHECK,
    "Building License": _HABITAT_SCOPE_CHECK,
    "Maintenance Work Order": _HABITAT_SCOPE_CHECK,
    "Maintenance Inspection Report": _HABITAT_SCOPE_CHECK,
    "Material Transfer": _HABITAT_SCOPE_CHECK,
    "Facility Asset Movement": _HABITAT_SCOPE_CHECK,
    "Custody Handover": _HABITAT_SCOPE_CHECK,
    "Facility Asset Delivery": _HABITAT_SCOPE_CHECK,
    "Occupancy Snapshot": _HABITAT_SCOPE_CHECK,
    "Temporary Worker": _HABITAT_SCOPE_CHECK,
    "Arrival Batch": _HABITAT_SCOPE_CHECK,
    "Room": _HABITAT_SCOPE_CHECK,
    "Bed": _HABITAT_SCOPE_CHECK,
    "Accommodation Stock Ledger": _HABITAT_SCOPE_CHECK,
    "Driver Attendance": _SALIS_SCOPE_CHECK,
    "Driver Suspension": _SALIS_SCOPE_CHECK,
    "Boarding Scan Log": _SALIS_SCOPE_CHECK,
    "Vehicle Damage Write-Off": _SALIS_SCOPE_CHECK,
    "Vehicle Incident": _SALIS_SCOPE_CHECK,
    "Driver Clearance": _SALIS_SCOPE_CHECK,
    "Vehicle Suspension": _SALIS_SCOPE_CHECK,
    "Movement Cost Transfer": _SALIS_SCOPE_CHECK,
    "Vehicle Handover": _SALIS_SCOPE_CHECK,
    "Wash Request": _SALIS_SCOPE_CHECK,
    "Fuel Daily Log": _SALIS_SCOPE_CHECK,
    "Rental Vehicle Movement": _SALIS_SCOPE_CHECK,
    "Movement Cost Recovery": _SALIS_SCOPE_CHECK,
    "Transport Trip Rating": _SALIS_SCOPE_CHECK,
    "Telecom Contract": _LOGISTAY_SCOPE_CHECK,
    "SIM Card": _LOGISTAY_SCOPE_CHECK,
    "SIM Custody Assignment": _LOGISTAY_SCOPE_CHECK,
    "Safety Incident": _HABITAT_SCOPE_CHECK,
    "Safety Inspection Report": _HABITAT_SCOPE_CHECK,
    "Safety Finding Ledger": _HABITAT_SCOPE_CHECK,
    "Cleaning Compliance Ledger": _HABITAT_SCOPE_CHECK,
}

fixtures = [
    {"dt": "Party Type", "filters": [["name", "in", ["Freelancer"]]]},
    {"dt": "Issue Type", "filters": [["name", "in", list(ISSUE_TYPES)]]},
    {"dt": "Issue Priority", "filters": [["name", "in", list(ISSUE_PRIORITIES)]]},
    {"dt": "Workflow State", "filters": [["name", "in", list(WORKFLOW_STATES)]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", list(WORKFLOW_ACTIONS)]]},
    {"dt": "Workflow", "filters": [["name", "in", list(WORKFLOWS)]]},
]

after_install = [
    "apex.setup.after_install",
    "apex.apex_core.setup.seed.seed_all",
    "apex.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    "apex.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    "apex.apex_core.setup.salis_support.grant_issue_role_permissions",
    "apex.apex_core.setup.app_owned_permissions_seed.seed_app_owned_permissions",
    "apex.apex_core.setup.employee_advance_recovery.seed_recovery_component",
    "apex.apex_core.setup.seeders.salis_settings_seed.seed_salis_settings",
    "apex.apex_core.setup.seeders.salis_portal_theme_seed.seed_salis_portal_theme",
    "apex.apex_core.setup.seeders.module_profile_seed.seed_module_profiles",
]

after_sync = []
after_migrate = [
    "apex.setup.after_migrate",
    "apex.apex_core.setup.salis_support.grant_issue_role_permissions",
    "apex.apex_core.setup.app_owned_permissions_seed.seed_app_owned_permissions",
    "apex.apex_core.setup.employee_advance_recovery.seed_recovery_component",
    "apex.apex_core.utils.employee_recovery.backfill_recovery_snapshots",
    "apex.apex_core.setup.seed.seed_all",
    "apex.apex_core.setup.seeders.habitat_auto_email_reports_seed.seed_auto_email_reports",
    "apex.apex_core.setup.seeders.salis_navbar_seed.seed_salis_navbar_help_links",
    "apex.apex_core.setup.seeders.salis_auto_email_reports_seed.seed_salis_auto_email_reports",
    "apex.apex_core.setup.seeders.salis_settings_seed.seed_salis_settings",
    "apex.apex_core.setup.seeders.salis_portal_theme_seed.seed_salis_portal_theme",
    "apex.apex_core.setup.seeders.module_profile_seed.seed_module_profiles",
    "apex.setup.create_roles",
    "apex.setup.create_role_profiles",
    "apex.apex_core.doctype.salis_settings.salis_settings.apply_approval_switch",
]

jinja = {
    "methods": [
        "apex.apex_core.utils.addresses.get_address_text",
        "apex.apex_core.utils.addresses.get_address_text_by_name",
        "apex.apex_core.doctype.masar_worker_token.masar_worker_token.doc_verify_qr",
        "apex.apex_core.doctype.masar_worker_token.masar_worker_token.masar_qr_data_uri",
    ],
}

get_changelog_feed = "apex.apex_core.utils.changelog.get_changelog_feed"
