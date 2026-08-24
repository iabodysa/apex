# Copyright (c) 2026, afmcoltd

import frappe


DOCTYPE = "Salis Settings"

DEFAULTS = {
    "enable_approvals": 1,
    "fuel_request_approval_threshold_litres": 100,
    "alert_lead_days": 7,
    "enable_driver_portal": 0,
}


def _sole(doctype, filters=None):
    rows = frappe.get_all(doctype, filters=filters or {}, pluck="name", limit=2)
    return rows[0] if len(rows) == 1 else None


def seed_salis_settings():
    if not frappe.db.exists("DocType", DOCTYPE):
        return []

    try:
        settings = frappe.get_single(DOCTYPE)
        stored = frappe.db.get_singles_dict(DOCTYPE)
        filled = []

        for field, value in DEFAULTS.items():
            if settings.meta.has_field(field) and field not in stored:
                settings.set(field, value)
                filled.append(field)

        if settings.meta.has_field("default_company") and "default_company" not in stored:
            company = _sole("Company")
            if company:
                settings.default_company = company
                filled.append("default_company")

        if settings.meta.has_field("default_cost_center") and "default_cost_center" not in stored:
            filters = {"is_group": 0}
            if settings.get("default_company"):
                filters["company"] = settings.get("default_company")
            cost_center = _sole("Cost Center", filters)
            if cost_center:
                settings.default_cost_center = cost_center
                filled.append("default_cost_center")

        if filled:
            settings.save()
            frappe.db.commit()
        return filled
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="salis_settings_seed failed", message=frappe.get_traceback()
        )
        return []
