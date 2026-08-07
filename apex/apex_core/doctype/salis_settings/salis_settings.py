# Copyright (c) 2026, afmcoltd
"""Salis Settings controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SalisSettings(Document):
    def validate(self):
        """Blocks a negative alert lead days value or fuel request approval threshold."""
        if self.alert_lead_days is not None and self.alert_lead_days < 0:
            frappe.throw(_("Alert Lead Days cannot be negative."))
        if (
            self.fuel_request_approval_threshold_litres is not None
            and self.fuel_request_approval_threshold_litres < 0
        ):
            frappe.throw(_("Fuel Request Approval Threshold cannot be negative."))


def get_salis_int(field: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``
    when the stored value is blank or zero (the new-Single-Int-stores-0 trap)."""
    try:
        value = frappe.db.get_single_value("Salis Settings", field)
    except Exception:
        return default
    if not value:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_salis_float(field: str, default: float) -> float:
    """Read a Float/Currency from the Salis Settings single, falling back to
    ``default`` when the stored value is blank or zero (the zero-trap)."""
    try:
        value = frappe.db.get_single_value("Salis Settings", field)
    except Exception:
        return default
    if not value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


BOARDING_FLOW_DEFAULTS = {
    "boarding_notify_max_count": 3,
    "boarding_notify_window_seconds": 60,
    "boarding_grace_minutes": 3,
    "boarding_auto_confirm_minutes": 15,
    "worker_wait_request_max": 3,
    "worker_wait_request_seconds": 60,
    "boarding_active_poll_seconds": 10,
}


def get_boarding_setting(key: str) -> int:
    """Return a boarding-flow Int setting, falling back to its built-in default
    when the stored value is blank or zero (the new-Single-Int-stores-0 trap)."""
    if key not in BOARDING_FLOW_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value("Salis Settings", key)
    return int(value) if value else BOARDING_FLOW_DEFAULTS[key]


def get_boarding_settings() -> dict:
    """All six boarding-flow tunables as a single dict (value-or-default applied),
    for the SPAs to fetch the limits/window/poll cadence in one read."""
    return {key: get_boarding_setting(key) for key in BOARDING_FLOW_DEFAULTS}


def get_default_company():
    """Resolve the company applied to Salis transactions when not set explicitly.

    Thin wrapper over the shared resolver (explicit Salis Settings default ->
    user company default -> global company default). Returns ``None`` when no
    company is configured (no posting is performed regardless).
    """
    from apex.apex_core.utils.company import resolve_company

    return resolve_company("Salis")


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
