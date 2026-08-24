# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import base64
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from apex.apex_core.setup.employee_advance_recovery import MAX_RECOVERY_PERCENT
from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.portal_bootstrap import portal_seed_color

_BRAND_LOGO_RE = re.compile(r"^/files/[^\"'<>\s]+$")


class SalisSettings(Document):
    def validate(self):
        if self.employee_advance_recovery_max_percent is not None and not (
            0 < self.employee_advance_recovery_max_percent <= MAX_RECOVERY_PERCENT
        ):
            frappe.throw(
                _(
                    "Maximum Recovery Percent must be greater than 0 and no more than {0}."
                ).format(int(MAX_RECOVERY_PERCENT))
            )
        if self.enable_employee_advance_recovery:
            if not self.employee_advance_recovery_component:
                frappe.throw(_("Recovery Salary Component is required to enable recovery."))
            component_type = frappe.db.get_value(
                "Salary Component", self.employee_advance_recovery_component, "type"
            )
            if component_type != "Deduction":
                frappe.throw(_("Recovery Salary Component must be a Deduction."))
        self._validate_web_push_public_key()
        self._validate_portal_appearance()
        self._validate_frontend_base_url()

    def on_update(self):
        apply_approval_switch()

    def _validate_portal_appearance(self):
        accent = (self.accent_color or "").strip()
        if accent and not portal_seed_color(accent):
            frappe.throw(_("Accent Color must be a hex colour such as #00844E."))

        logo = (self.brand_logo or "").strip()
        if logo and not _BRAND_LOGO_RE.match(logo):
            frappe.throw(_("Brand Logo must be an uploaded file (a /files/ path)."))

    def _validate_web_push_public_key(self):
        if not self.enable_web_push:
            return
        raw = (self.web_push_vapid_public_key or "").strip()
        if not raw:
            frappe.throw(_("A Web Push VAPID public key is required to enable web push."))
        padded = raw.replace("-", "+").replace("_", "/")
        padded += "=" * ((4 - len(padded) % 4) % 4)
        try:
            point = base64.b64decode(padded)
        except (ValueError, TypeError):
            frappe.throw(_("The Web Push VAPID public key is not valid base64url."))
        if len(point) != 65 or point[0] != 4:
            frappe.throw(
                _(
                    "The Web Push VAPID public key must decode to 65 bytes starting with 0x04; "
                    "this one decodes to {0}. Paste the uncompressed public key, not a "
                    "truncated or DER-encoded one."
                ).format(len(point))
            )

    def _validate_frontend_base_url(self):
        url = (self.frontend_base_url or "").strip()
        if not url:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            frappe.throw(
                _("Frontend Base URL must start with http:// or https:// (for example https://salis-fleet.com).")
            )


def apply_approval_switch():
    if not frappe.db.exists("DocType", "Workflow"):
        return
    enabled = cint(frappe.db.get_single_value("Salis Settings", "enable_approvals"))
    salis_doctypes = frappe.get_all("DocType", filters={"module": "Salis"}, pluck="name")
    if not salis_doctypes:
        return
    for name in frappe.get_all(
        "Workflow", filters={"document_type": ["in", salis_doctypes]}, pluck="name"
    ):
        if cint(frappe.db.get_value("Workflow", name, "is_active")) != enabled:
            frappe.db.set_value("Workflow", name, "is_active", enabled)
            frappe.clear_cache(doctype=frappe.db.get_value("Workflow", name, "document_type"))


def get_salis_int(field: str, default: int) -> int:
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
    if key not in BOARDING_FLOW_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value("Salis Settings", key)
    return int(value) if value else BOARDING_FLOW_DEFAULTS[key]


def get_boarding_settings() -> dict:
    return {key: get_boarding_setting(key) for key in BOARDING_FLOW_DEFAULTS}


def get_default_cost_center():
    cost_center = frappe.db.get_single_value("Salis Settings", "default_cost_center")
    if not cost_center:
        company = resolve_company("Salis")
        if company and frappe.db.exists("Company", company):
            cost_center = frappe.get_cached_value("Company", company, "cost_center")
    return cost_center or None
