"""Salis Settings controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SalisSettings(Document):
    def validate(self):
        if self.alert_lead_days is not None and self.alert_lead_days < 0:
            frappe.throw(_("Alert Lead Days cannot be negative."))
        if (
            self.fuel_request_approval_threshold_litres is not None
            and self.fuel_request_approval_threshold_litres < 0
        ):
            frappe.throw(_("Fuel Request Approval Threshold cannot be negative."))


def get_salis_settings():
    return frappe.get_single("Salis Settings")


def get_default_company():
    """Resolve the company applied to Salis transactions when not set explicitly.

    Mirrors Habitat's defaulting order: the explicit Salis Settings default first,
    then the user's company default, then the global company default. Returns
    ``None`` when no company is configured (no posting is performed regardless).
    """
    company = frappe.db.get_single_value("Salis Settings", "default_company")
    if not company:
        company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.defaults.get_global_default("company")
    return company or None


def get_default_cost_center():
    """Resolve the default cost center for fleet cost references.

    Falls back from the explicit Salis Settings default to the resolved
    company's own default cost center. Returns ``None`` when none is configured.
    """
    cost_center = frappe.db.get_single_value("Salis Settings", "default_cost_center")
    if not cost_center:
        company = get_default_company()
        if company and frappe.db.exists("Company", company):
            cost_center = frappe.get_cached_value("Company", company, "cost_center")
    return cost_center or None
