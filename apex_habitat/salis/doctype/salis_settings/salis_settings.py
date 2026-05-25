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
    company = frappe.db.get_single_value("Salis Settings", "default_company")
    if not company:
        company = frappe.defaults.get_global_default("company")
    return company
