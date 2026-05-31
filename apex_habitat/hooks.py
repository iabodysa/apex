# Package name (internal identifier) stays "apex_habitat" — renaming the package is a
# breaking, major change. The user-facing title is decoupled from the Habitat module:
# "Apex" hosts the Habitat (accommodation) and Salis (movement/fleet) modules.
app_name = "apex_habitat"
app_title = "Apex"
app_publisher = "AFMCO Support Services Co. Ltd"
app_description = "Apex — workforce operations suite: Habitat (accommodation & facilities) and Salis (movement & fleet)."
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
        "before_save": "apex_habitat.apex_core.doctype.habitat_settings.habitat_settings.before_save",
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
        "apex_habitat.salis.tasks.reconcile_operations_alerts",
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

# Salis: project-based row scoping — supervisors/PMs see only
# the projects they hold a User Permission for; oversight roles see all.
permission_query_conditions = {
    "Vehicle Assignment": "apex_habitat.salis.permissions.vehicle_assignment_query",
    "Fuel Request": "apex_habitat.salis.permissions.fuel_request_query",
    "Dispatch Trip": "apex_habitat.salis.permissions.dispatch_trip_query",
    "Trip Start Log": "apex_habitat.salis.permissions.trip_start_log_query",
    "Transport Request": "apex_habitat.salis.permissions.transport_request_query",
    "Route Plan": "apex_habitat.salis.permissions.route_plan_query",
    "Support Ticket": "apex_habitat.salis.permissions.support_ticket_query",
    "Fuel Claim": "apex_habitat.salis.permissions.fuel_claim_query",
    "Fuel Quota": "apex_habitat.salis.permissions.fuel_quota_query",
    "Fuel Exception Case": "apex_habitat.salis.permissions.fuel_exception_case_query",
    "Salis Payment Request": "apex_habitat.salis.permissions.salis_payment_request_query",
    "Salis Vehicle": "apex_habitat.salis.permissions.salis_vehicle_query",
    "Salis Driver": "apex_habitat.salis.permissions.salis_driver_query",
    "Passenger Manifest": "apex_habitat.salis.permissions.passenger_manifest_query",
}

has_permission = {
    "Vehicle Assignment": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Dispatch Trip": "apex_habitat.salis.permissions.scoped_has_permission",
    "Trip Start Log": "apex_habitat.salis.permissions.scoped_has_permission",
    "Transport Request": "apex_habitat.salis.permissions.scoped_has_permission",
    "Route Plan": "apex_habitat.salis.permissions.scoped_has_permission",
    "Support Ticket": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Claim": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Quota": "apex_habitat.salis.permissions.scoped_has_permission",
    "Fuel Exception Case": "apex_habitat.salis.permissions.scoped_has_permission",
    "Salis Payment Request": "apex_habitat.salis.permissions.payment_sod_has_permission",
    "Salis Vehicle": "apex_habitat.salis.permissions.scoped_has_permission",
}

# Fixtures shipped with the app
fixtures = [
    {"dt": "Safety Task Catalog"},
    {"dt": "Role", "filters": [["name", "in", ["Accommodation Manager", "Resident Supervisor", "Finance Manager", "Internal Auditor"]]]},
    # Salis (Movement) custom roles — only the uniquely-ours, post-consolidation
    # roles are fixtured. Core/generic roles (Fleet Manager, Driver) are
    # existence-guarded in the seeds, never fixtured, to avoid clobbering
    # ERPNext/HRMS-owned roles. The merged roles (Fleet Operations Manager,
    # Fleet Regional Manager, Legal Officer) are intentionally NOT fixtured —
    # see patches/v1_x/consolidate_salis_roles.py.
    {"dt": "Role", "filters": [["name", "in", ["Fleet Project Manager", "Fleet Supervisor", "Government Relations Officer"]]]},
    # Print Format and Web Form are standard module files (is_standard=1)
    # under habitat/print_format/ and habitat/web_form/ — loaded automatically
    # by bench migrate via import_file, no fixture entry needed.
]

# First-install bootstrap: Habitat + Salis (each existence-guarded/idempotent).
after_install = [
    "apex_habitat.setup.after_install",
    "apex_habitat.salis.setup.after_install",
    # Salis native paradigms — Notifications, Kanban Boards, Assignment Rules.
    # Idempotent + existence-guarded; mirrors Habitat (which seeds the equivalents
    # from setup.after_install). The same functions also run on after_migrate and
    # from the v1_1 patch (single source of truth), so replaying them is safe.
    "apex_habitat.salis.notifications_seed.seed_salis_notifications",
    "apex_habitat.salis.kanban_seed.seed_salis_kanban_boards",
    "apex_habitat.salis.assignment_rules_seed.seed_salis_assignment_rules",
    # Salis navbar Help-dropdown links — mirrors Habitat's add_navbar_help_links
    # patch (Navbar Settings is a Single, never fixtured; additive + idempotent,
    # never clobbers the customer's navbar). Surfaces the Salis workspace and the
    # Dispatch Board page one click away from the desk Help menu.
    "apex_habitat.salis.navbar_seed.seed_salis_navbar_help_links",
    # Salis communication artifacts — Email Templates + Auto Email Reports.
    # Mirrors Habitat's email_templates_seed / auto_email_reports_seed. Idempotent
    # + existence-guarded (Auto Email Reports created disabled, addressed to
    # Administrator as a placeholder). Also run on after_migrate and from the
    # v1_x patch (single source of truth), so replaying them is safe.
    "apex_habitat.salis.email_templates_seed.seed_salis_email_templates",
    "apex_habitat.salis.auto_email_reports_seed.seed_salis_auto_email_reports",
    # Salis native Workflow Spine — Transport Request (first-mover). Frappe does
    # not auto-import a Workflow from a module folder, so the shipped JSON is
    # applied by this idempotent, existence-guarded seed (also run on
    # after_migrate and from the v1_x patch — single source of truth).
    "apex_habitat.salis.workflow_seed.seed_salis_workflows",
]
# Dashboards seed after migrate (when their charts/number cards already exist).
after_migrate = [
    "apex_habitat.habitat.dashboard_seed.seed_all_dashboards",
    "apex_habitat.salis.dashboard_seed.seed_salis_dashboards",
    "apex_habitat.salis.movement_dashboard_seed.seed_movement_dashboards",
    # Habitat operational Notifications — keep already-installed sites in sync on
    # migrate (idempotent, existence-guarded, created disabled). Single source of
    # truth; also run from setup.after_install and the v1_x seed patch. Reliable
    # because after_migrate runs after every DocType sync, so a freshly-added
    # notification's document_type always exists by the time this runs.
    "apex_habitat.habitat.notifications_seed.seed_operational_notifications",
    # Habitat native paradigms — these were install-only (after_install) so a
    # newly-added kanban / assignment rule / email template / auto-email report
    # never reached already-installed sites. They are idempotent + existence-
    # guarded; running them on every migrate keeps existing sites in sync, matching
    # the Salis equivalents below.
    "apex_habitat.habitat.kanban_seed.seed_kanban_boards",
    "apex_habitat.habitat.assignment_rules_seed.seed_assignment_rules",
    "apex_habitat.habitat.email_templates_seed.seed_email_templates",
    "apex_habitat.habitat.auto_email_reports_seed.seed_auto_email_reports",
    # Salis native paradigms — keep already-installed sites in sync on migrate.
    # Idempotent + existence-guarded (created only if absent), so re-running every
    # migrate never duplicates and never aborts the migrate.
    "apex_habitat.salis.notifications_seed.seed_salis_notifications",
    "apex_habitat.salis.kanban_seed.seed_salis_kanban_boards",
    "apex_habitat.salis.assignment_rules_seed.seed_salis_assignment_rules",
    # Salis navbar Help-dropdown links — keep already-installed sites in sync on
    # migrate (idempotent; appends only the links that are missing).
    "apex_habitat.salis.navbar_seed.seed_salis_navbar_help_links",
    # Salis communication artifacts — keep already-installed sites in sync on
    # migrate (idempotent + existence-guarded; created only if absent).
    "apex_habitat.salis.email_templates_seed.seed_salis_email_templates",
    "apex_habitat.salis.auto_email_reports_seed.seed_salis_auto_email_reports",
    # Salis native Workflow Spine — keep already-installed sites in sync on
    # migrate (idempotent + existence-guarded; created only if absent, never
    # clobbers an on-site-tuned Workflow).
    "apex_habitat.salis.workflow_seed.seed_salis_workflows",
]

# A fresh test site has no Company or ERPNext master data until the setup wizard
# runs, so any test that inserts a Company would fail (Warehouse Type "Transit"
# missing). This hook provisions the site once before the suite runs — see
# apex_habitat/tests/before_tests.py.
before_tests = "apex_habitat.tests.before_tests.before_tests"

# Frappe What's New feed — appears in desk notification area, not as a popup
get_changelog_feed = "apex_habitat.habitat.utils.changelog.get_changelog_feed"
