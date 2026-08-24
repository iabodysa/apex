# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

_MODULE_COMPANY_FIELD = {
    "Habitat": ("Habitat Settings", "company"),
    "Salis": ("Salis Settings", "default_company"),
}


def resolve_company(module: str | None = None) -> str | None:
    company = None
    if module:
        single, field = _MODULE_COMPANY_FIELD[module]
        company = frappe.db.get_single_value(single, field)
    if not company:
        company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.defaults.get_global_default("company")
    return company or None


def company_for_building(building: str | None, module: str = "Habitat") -> str | None:
    company = None
    if building:
        company = frappe.db.get_value("Building", building, "company")
    return company or resolve_company(module)


def company_for_vehicle(vehicle: str | None, module: str = "Salis") -> str | None:
    company = None
    if vehicle:
        company = frappe.db.get_value("Salis Vehicle", vehicle, "company")
    return company or resolve_company(module)


def company_for_trip(dispatch_trip: str | None, module: str = "Salis") -> str | None:
    vehicle = None
    if dispatch_trip:
        vehicle = frappe.db.get_value("Dispatch Trip", dispatch_trip, "vehicle")
    return company_for_vehicle(vehicle, module)


def resolve_company_or_any(module: str | None = None) -> str | None:
    return resolve_company(module) or (
        frappe.get_all("Company", pluck="name", limit=1) or [None]
    )[0]


def display_currency(module: str = "Habitat") -> str:
    company = resolve_company(module)
    if company:
        currency = frappe.get_cached_value("Company", company, "default_currency")
        if currency:
            return currency
    return frappe.db.get_default("currency") or frappe.defaults.get_global_default("currency") or ""
