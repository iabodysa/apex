# Copyright (c) 2026, afmcoltd
"""Shared company resolver.

One defaulting chain for the company applied to a transaction when it is not set
explicitly, shared by Habitat and Salis so both modules resolve a company the same
way:

    explicit module setting  ->  user company default  ->  global company default

Pure refactor of the chain that was duplicated across the two settings controllers
(and partly re-implemented at call sites such as ``arrivals_desk``). The
per-module setting is read with ``get_single_value`` so this util does not import,
load, or edit the Habitat/Salis Settings DocTypes — it only reads their stored
value through the field whose name each module uses.

Returns ``None`` when no company is configured anywhere; callers treat that as
"no company known" and post nothing that requires one.
"""

from __future__ import annotations

import frappe

_MODULE_COMPANY_FIELD = {
    "Habitat": ("Habitat Settings", "company"),
    "Salis": ("Salis Settings", "default_company"),
}


def resolve_company(module: str | None = None) -> str | None:
    """Resolve a company via explicit module setting -> user default -> global default.

    ``module`` (``"Habitat"`` / ``"Salis"``) selects which Single's explicit
    company field to consult first; ``None`` skips the module step and starts at
    the user default. Returns ``None`` when nothing is configured.
    """
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
    """Company for a building-scoped ledger row: the Accommodation Building's own
    ``company`` Link, else the module default chain."""
    company = None
    if building:
        company = frappe.db.get_value("Building", building, "company")
    return company or resolve_company(module)


def company_for_vehicle(vehicle: str | None, module: str = "Salis") -> str | None:
    """Company for a vehicle-scoped ledger row: the Salis Vehicle's own ``company``
    Link, else the module default chain."""
    company = None
    if vehicle:
        company = frappe.db.get_value("Salis Vehicle", vehicle, "company")
    return company or resolve_company(module)


def company_for_trip(dispatch_trip: str | None, module: str = "Salis") -> str | None:
    """Company for a trip-scoped ledger row: the trip vehicle's ``company``, else
    the module default chain."""
    vehicle = None
    if dispatch_trip:
        vehicle = frappe.db.get_value("Dispatch Trip", dispatch_trip, "vehicle")
    return company_for_vehicle(vehicle, module)


def resolve_company_or_any(module: str | None = None) -> str | None:
    """Demo/seed last resort: ``resolve_company``, else ANY existing Company.

    The ``any Company`` tail exists only so demo/seed paths have SOME company to
    attach on a bench where no default is configured yet. Never use in real
    transaction posting — an arbitrary company is meaningless for ownership.
    """
    return resolve_company(module) or (
        frappe.get_all("Company", pluck="name", limit=1) or [None]
    )[0]
