"""Seed Salis Settings default values.

Idempotent and install-safe: only fills BLANK fields (never clobbers an
admin's later edits), links default_company / default_cost_center only when
exactly one exists, skips gracefully if the Salis Settings DocType is not yet
migrated, and wraps everything so it can never fail an install/migrate.
"""

import frappe

DEFAULTS = {
    "enable_approvals": 1,
    "cross_project_needs_approval": 1,
    "fuel_request_approval_threshold_litres": 100,
    "alert_lead_days": 7,
    "enable_driver_portal": 0,
}


def execute():
    try:
        # Skip-missing: module/doctype not migrated yet on this site.
        if not frappe.db.exists("DocType", "Salis Settings"):
            return

        settings = frappe.get_single("Salis Settings")
        changed = False

        # Only fill blanks — respect any value an admin already set.
        for field, value in DEFAULTS.items():
            if settings.meta.has_field(field) and not settings.get(field):
                settings.set(field, value)
                changed = True

        # Skip-missing dependencies: link a Company only if exactly one exists.
        if settings.meta.has_field("default_company") and not settings.get(
            "default_company"
        ):
            companies = frappe.get_all("Company", pluck="name", limit=2)
            if len(companies) == 1:
                settings.default_company = companies[0]
                changed = True

        # Cost Center only if exactly one (non-group) exists for the chosen company.
        if settings.meta.has_field("default_cost_center") and not settings.get(
            "default_cost_center"
        ):
            cc_filters = {"is_group": 0}
            if settings.get("default_company"):
                cc_filters["company"] = settings.get("default_company")
            cost_centers = frappe.get_all(
                "Cost Center", filters=cc_filters, pluck="name", limit=2
            )
            if len(cost_centers) == 1:
                settings.default_cost_center = cost_centers[0]
                changed = True

        if changed:
            settings.save(ignore_permissions=True)  # audit-ok
            frappe.db.commit()
    except Exception:
        # A seed must NEVER crash install/migrate — log and continue.
        frappe.db.rollback()
        frappe.log_error(
            title="seed_salis_settings failed",
            message=frappe.get_traceback(),
        )
