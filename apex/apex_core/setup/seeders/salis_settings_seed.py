# Copyright (c) 2026, afmcoltd
"""Seed Salis Settings defaults. Install-safe, idempotent, blank-fields-only.

This lived in ``patches/v1_0/seed_salis_settings.py``, which ``salis/setup.py`` imported
to run at install time. A patch is a one-time migration for sites that already exist; the
defaults every NEW site needs belong beside the other seeders, and hooks.py runs this on
both after_install and after_migrate.

Only BLANK fields are filled, so an administrator's later edit is never clobbered.
``default_company`` and ``default_cost_center`` are linked ONLY when exactly one candidate
exists — with two or more there is no safe guess, and a wrong default on a money field is
worse than an empty one the operator has to fill.

The failure is swallowed rather than raised because this same function runs on EVERY
migrate: a run that silently did nothing is re-attempted by the next one, so it is never
the last chance to fill these defaults. A seed with no such re-run must raise instead.
"""

import frappe

DOCTYPE = "Salis Settings"

DEFAULTS = {
    "enable_approvals": 1,
    "cross_project_needs_approval": 1,
    "fuel_request_approval_threshold_litres": 100,
    "alert_lead_days": 7,
    "enable_driver_portal": 0,
}


def _sole(doctype, filters=None):
    """The only candidate of ``doctype``, or None when there are none or several."""
    rows = frappe.get_all(doctype, filters=filters or {}, pluck="name", limit=2)
    return rows[0] if len(rows) == 1 else None


def seed_salis_settings():
    """Fill any blank Salis Settings default. Returns the fieldnames set on this call."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return []

    try:
        settings = frappe.get_single(DOCTYPE)
        filled = []

        for field, value in DEFAULTS.items():
            if settings.meta.has_field(field) and not settings.get(field):
                settings.set(field, value)
                filled.append(field)

        if settings.meta.has_field("default_company") and not settings.get("default_company"):
            company = _sole("Company")
            if company:
                settings.default_company = company
                filled.append("default_company")

        if settings.meta.has_field("default_cost_center") and not settings.get(
            "default_cost_center"
        ):
            filters = {"is_group": 0}
            if settings.get("default_company"):
                filters["company"] = settings.get("default_company")
            cost_center = _sole("Cost Center", filters)
            if cost_center:
                settings.default_cost_center = cost_center
                filled.append("default_cost_center")

        if filled:
            settings.save(ignore_permissions=True)
            frappe.db.commit()
        return filled
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="salis_settings_seed failed", message=frappe.get_traceback()
        )
        return []
