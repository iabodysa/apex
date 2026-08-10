# Copyright (c) 2026, afmcoltd
"""Merged Habitat portal served at /housing, and through www/safety.py at /safety.

One mobile-first supervisor surface for a whole housing and safety day: the Housing
Inventory count, the three-exit Facility Asset Delivery clearance, the building bed
board, the custody kiosk, arrivals intake, bed transfers, and the safety round.

Admission is the UNION of the two former role sets, because both doors already
redirect a guest to /login and both gate on a role set — one identity model, one
portal. What a user then SEES is decided here from the DocPerms the endpoints
themselves enforce, and shipped to the page as a section list. Hiding a section in
the client is presentation only; every read and write is refused again by its own
endpoint, and the building scope still confines a supervisor to their own estate.

The gate lives in this module because it serves both doors. www/safety.py is the
second door and imports it rather than keeping a second copy.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_language import render_in_arabic
from apex.apex_core.utils.portal_bootstrap import (
    apply_portal_appearance,
    guest_redirect,
)

HOUSING_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Procurement Supervisor",
}

SAFETY_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Safety Officer",
}

PORTAL_ROLES = HOUSING_ROLES | SAFETY_ROLES


def has_apps_screen_access() -> bool:
    """Gate for the /apps tiles — the same union check get_context applies, so a tile
    never advertises a page the portal would turn away."""
    return bool(PORTAL_ROLES & set(frappe.get_roles()))


def _can(doctype: str, *ptypes: str) -> bool:
    """True only when the caller holds every named permission type on the doctype."""
    return all(frappe.has_permission(doctype, ptype) for ptype in ptypes)


def _clearable_exits() -> list:
    """The exit numbers this caller may actually clear.

    Write on the delivery is not the gate — each exit is held by its own role
    (``api.facility_asset_delivery.EXIT_ROLES``), so a screen that offered the button on
    write alone showed a Procurement Supervisor a large green control that only a Resident
    Supervisor may press, and the refusal arrived after the tap.
    """
    from apex.habitat.api.facility_asset_delivery import EXIT_ROLES

    if not _can("Facility Asset Delivery", "write"):
        return []
    roles = set(frappe.get_roles())
    if "System Manager" in roles:
        return sorted(EXIT_ROLES)
    return sorted(number for number, role in EXIT_ROLES.items() if role in roles)


def portal_capabilities() -> dict:
    """The per-action grants a section needs, so a control can be disabled with a
    stated reason instead of failing at the server."""
    return {
        "count": _can("Housing Inventory", "read", "write"),
        "clear_exit": _can("Facility Asset Delivery", "write"),
        "exits": _clearable_exits(),
        "set_readiness": _can("Room", "write"),
        "check_in": _can("Housing Assignment", "create", "submit"),
        "check_out": _can("Housing Checkout", "create", "submit"),
        "issue_custody": _can("Custody Issue", "create", "submit"),
        "return_custody": _can("Custody Return", "create", "submit"),
        "register_worker": _can("Temporary Worker", "create"),
        "transfer": _can("Room Bed Transfer", "create", "submit"),
        "record_round": _can("Safety Task Execution", "create"),
        "submit_round": _can("Safety Task Execution", "submit"),
    }


def portal_sections() -> list[str]:
    """The sections this user may actually work, in nav order.

    Each test names the permission the section's own endpoints already enforce, so a
    role reaches only screens it can use: Procurement Supervisor holds the delivery
    and nothing else, Safety Officer holds the round and nothing else, and the three
    shared roles get both halves at one address instead of two.
    """
    reads_estate = _can("Building", "read")
    sections = []
    if reads_estate and _can("Housing Inventory", "read"):
        sections.append("count")
    if _can("Facility Asset Delivery", "read"):
        sections.append("delivery")
    if reads_estate and _can("Room", "read") and _can("Bed", "read"):
        sections.append("beds")
    if reads_estate and _can("Housing Assignment", "create", "submit"):
        sections.append("arrivals")
    if _can("Custody Issue", "read") and _can("Custody Article", "read"):
        sections.append("custody")
    if reads_estate and _can("Room Bed Transfer", "create", "submit"):
        sections.append("transfer")
    if reads_estate and _can("Safety Task Catalog", "read"):
        sections.append("safety")
    return sections


def bootstrap_portal_context(context, route: str, entry: str):
    """Redirect a guest to login, then publish the merged portal's gate and its
    realtime configuration for whichever door was opened."""
    guest_redirect(route)
    render_in_arabic()

    context.no_cache = 1
    apply_portal_appearance(context)
    context.portal_entry = entry
    context.has_portal_role = bool(PORTAL_ROLES & set(frappe.get_roles()))
    if not context.has_portal_role:
        return context

    context.csrf_token = get_csrf_token()
    context.portal_sections = portal_sections()
    context.portal_capabilities = portal_capabilities()
    conf = frappe.get_site_config()
    context.site_name = frappe.local.site
    context.socketio_port = cint(conf.get("socketio_port")) or 9000
    context.async_enabled = not cint(conf.get("disable_async"))
    context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context


def get_context(context):
    """Bootstraps the merged portal at its housing door."""
    return bootstrap_portal_context(context, "/housing", "housing")
