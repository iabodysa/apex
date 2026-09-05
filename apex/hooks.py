# Copyright (c) 2026, afmcoltd

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

website_redirects = [{"source": "/housing-count", "target": "/housing#/count"}]

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

_WORKFLOW_GUARD = "apex.apex_core.setup.app_owned_workflows.refuse_shipped_workflow_edit"

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
        "validate": _WORKFLOW_GUARD,
        "before_rename": _WORKFLOW_GUARD,
        "on_trash": _WORKFLOW_GUARD,
    },
    "Workflow Document State": {"validate": _WORKFLOW_GUARD},
    "Workflow Transition": {"validate": _WORKFLOW_GUARD},
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
    "Maintenance Request": {
        "validate": "apex.habitat.doctype.maintenance_request.maintenance_request.validate",
    },
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
    "Facility Asset Movement": {
        "validate": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.validate",
        "on_submit": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.on_submit",
        "before_cancel": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.before_cancel",
        "on_cancel": "apex.habitat.doctype.facility_asset_movement.facility_asset_movement.on_cancel",
    },
    "Subcontractor Service Order": {
        "before_save": "apex.habitat.doctype.subcontractor_service_order.subcontractor_service_order.before_save",
    },
    "Habitat Settings": {
        "before_save": "apex.apex_core.doctype.habitat_settings.habitat_settings.before_save",
    },
    "Maintenance Work Order": {
        "validate": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.validate",
        "on_submit": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.on_submit",
        "before_cancel": "apex.habitat.doctype.maintenance_work_order.maintenance_work_order.before_cancel",
    },
    "Scheduled Task Instance": {
        "on_submit": "apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance.on_submit",
        "before_cancel": "apex.habitat.doctype.scheduled_task_instance.scheduled_task_instance.before_cancel",
    },
    "Maintenance Inspection Report": {
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

_HABITAT_NO_BUILDING_DOCTYPES = (
    "Housing Assignment", "Custody Issue", "Cleaning Log", "Building", "Safety Round",
    "Safety Task Execution", "Scheduled Task Instance", "Resident Request",
    "Idle Resident Report", "Facility Asset Custody Assignment",
    "Operational Depreciation Snapshot", "Custody Return", "Custody Damage Assessment",
    "Custody Acknowledgment", "Facility Asset", "Housing Inventory",
    "Building License", "Maintenance Work Order", "Maintenance Inspection Report",
    "Occupancy Snapshot", "Temporary Worker", "Arrival Batch", "Room", "Bed",
    "Accommodation Stock Ledger", "Safety Incident", "Safety Inspection Report",
    "Safety Finding Ledger", "Cleaning Compliance Ledger",
)

_HABITAT_SCOPE_QUERY_DOCTYPES = (
    "Housing Checkout", "Room Bed Transfer", "Audit Remediation Plan",
    "Material Transfer", "Facility Asset Movement", "Custody Handover",
    "Facility Asset Delivery",
)

_SALIS_SCOPE_DOCTYPES = (
    "Vehicle Assignment", "Fuel Request", "Dispatch Trip", "Trip Start Log",
    "Transport Request", "Route Assignment", "Route Plan", "Issue", "Fuel Claim",
    "Fuel Quota", "Fuel Exception Case", "Salis Payment Request", "Salis Vehicle",
    "Salis Driver", "Passenger Manifest", "Driver Attendance", "Driver Suspension",
    "Boarding Scan Log", "Vehicle Damage Write-Off", "Vehicle Incident",
    "Driver Clearance", "Vehicle Suspension", "Movement Cost Transfer",
    "Vehicle Handover", "Wash Request", "Fuel Daily Log", "Rental Vehicle Movement",
    "Movement Cost Recovery", "Transport Trip Rating",
)

_SALIS_SCOPE_QUERY_ONLY_DOCTYPES = (
    "Fuel Consumption Ledger", "Rental Accrual Ledger", "Vehicle Utilisation Snapshot",
)

_LOGISTAY_SCOPE_DOCTYPES = (
    "Telecom Contract", "SIM Card", "SIM Custody Assignment",
)

permission_query_conditions = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_query",
    **dict.fromkeys(_HABITAT_NO_BUILDING_DOCTYPES, _HABITAT_NO_BUILDING_QUERY),
    **dict.fromkeys(_HABITAT_SCOPE_QUERY_DOCTYPES, _HABITAT_SCOPE_QUERY),
    **dict.fromkeys(_SALIS_SCOPE_DOCTYPES, _SALIS_SCOPE_QUERY),
    **dict.fromkeys(_SALIS_SCOPE_QUERY_ONLY_DOCTYPES, _SALIS_SCOPE_QUERY),
    "Masar Worker Token": "apex.apex_core.utils.portal_identity.masar_worker_token_scope_query",
    "Portal Device": "apex.apex_core.utils.portal_identity.portal_device_scope_query",
    "Portal Push Subscription": "apex.apex_core.utils.portal_identity.portal_push_subscription_scope_query",
    **dict.fromkeys(_LOGISTAY_SCOPE_DOCTYPES, _LOGISTAY_SCOPE_QUERY),
}

has_permission = {
    "Maintenance Request": "apex.habitat.permissions.maintenance_request_has_permission",
    **dict.fromkeys(_HABITAT_NO_BUILDING_DOCTYPES + _HABITAT_SCOPE_QUERY_DOCTYPES, _HABITAT_SCOPE_CHECK),
    **dict.fromkeys(_SALIS_SCOPE_DOCTYPES, _SALIS_SCOPE_CHECK),
    "Masar Worker Token": "apex.apex_core.utils.portal_identity.masar_worker_token_has_permission",
    "Portal Device": "apex.apex_core.utils.portal_identity.portal_device_has_permission",
    "Portal Push Subscription": "apex.apex_core.utils.portal_identity.portal_push_subscription_has_permission",
    **dict.fromkeys(_LOGISTAY_SCOPE_DOCTYPES, _LOGISTAY_SCOPE_CHECK),
}

fixtures = [
    {"dt": "Party Type", "filters": [["name", "in", ["Freelancer"]]]},
    {
        "dt": "Role Profile",
        "filters": [
            [
                "name",
                "in",
                [
                    "Habitat Accommodation Manager",
                    "Habitat Cleaning Supervisor",
                    "Habitat Finance Reviewer",
                    "Habitat Maintenance Technician",
                    "Habitat Resident Request Coordinator",
                    "Habitat Resident Supervisor",
                    "Habitat Safety Officer",
                    "Salis Driver",
                ],
            ]
        ],
    },
    {"dt": "Issue Type", "filters": [["name", "in", list(ISSUE_TYPES)]]},
    {"dt": "Issue Priority", "filters": [["name", "in", list(ISSUE_PRIORITIES)]]},
    {"dt": "Workflow State", "filters": [["name", "in", list(WORKFLOW_STATES)]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", list(WORKFLOW_ACTIONS)]]},
    {"dt": "Workflow", "filters": [["name", "in", list(WORKFLOWS)]]},
    {
        "dt": "Custody Asset Category",
        "filters": [
            [
                "name",
                "in",
                [
                    "Bedding & Linen",
                    "Room Access",
                    "Remote Controls",
                    "Furniture",
                    "Cleaning Tools",
                    "Safety Equipment",
                    "Facility Keys",
                ],
            ]
        ],
    },
    {
        "dt": "Custody Article",
        "filters": [
            [
                "name",
                "in",
                [
                    "Room Key",
                    "Gate Access Card",
                    "Locker Key",
                    "Blanket",
                    "Pillow",
                    "Bed Sheet",
                    "Mattress Protector",
                    "AC Remote",
                    "TV Remote",
                    "Padlock",
                ],
            ]
        ],
    },
    {
        "dt": "Operational Depreciation Policy",
        "filters": [
            [
                "name",
                "in",
                [
                    "Linen - 12 Months",
                    "Keys and Cards - 24 Months",
                    "Remotes - 24 Months",
                    "Furniture - 36 Months",
                    "Electronics - 36 Months",
                ],
            ]
        ],
    },
    {
        "dt": "Safety Task Catalog",
        "filters": [
            [
                "name",
                "in",
                [
                    "CMP-01",
                    "CMP-02",
                    "CMP-03",
                    "CMP-04",
                    "CMP-05",
                    "CMP-06",
                    "CMP-07",
                    "DOC-01",
                    "DOC-02",
                    "DOC-03",
                    "DOC-04",
                    "DOC-05",
                    "DOC-06",
                    "DOC-07",
                    "EMR-01",
                    "EMR-02",
                    "EMR-03",
                    "EMR-04",
                    "EMR-05",
                    "EMR-06",
                    "EMR-07",
                    "FIRE-01",
                    "FIRE-02",
                    "FIRE-03",
                    "FIRE-04",
                    "FIRE-05",
                    "FIRE-06",
                    "FIRE-07",
                    "FIRE-08",
                    "HH-01",
                    "HH-02",
                    "HH-03",
                    "HH-04",
                    "HH-05",
                    "HH-06",
                    "HH-07",
                    "HH-08",
                    "MNT-01",
                    "MNT-02",
                    "MNT-03",
                    "MNT-04",
                    "MNT-05",
                    "MNT-06",
                    "MNT-07",
                    "MNT-08",
                    "SEC-01",
                    "SEC-02",
                    "SEC-03",
                    "SEC-04",
                    "SEC-05",
                    "SEC-06",
                    "SEC-07",
                    "SEC-08",
                    "TRN-01",
                    "TRN-02",
                    "TRN-03",
                    "TRN-04",
                    "TRN-05",
                    "TRN-06",
                    "TRN-07",
                ],
            ]
        ],
    },
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
    "apex.apex_core.utils.portal_identity.close_all_capacity_desk_access",
]

after_sync = [
    "apex.apex_core.doctype.salis_settings.salis_settings.apply_approval_switch",
]
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
    "apex.apex_core.utils.portal_identity.close_all_capacity_desk_access",
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
