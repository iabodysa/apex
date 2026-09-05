# Copyright (c) 2026, Apex contributors

import frappe
from apex.apex_core.utils.portal_bootstrap import (
    guest_redirect,
    publish_portal_context,
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
    return bool(PORTAL_ROLES & set(frappe.get_roles()))

def _can(doctype: str, *ptypes: str) -> bool:
    return all(frappe.has_permission(doctype, ptype) for ptype in ptypes)

def _clearable_exits() -> list:
    from apex.habitat.api.facility_asset_delivery import EXIT_ROLES

    if not _can("Facility Asset Delivery", "write"):
        return []
    roles = set(frappe.get_roles())
    if "System Manager" in roles:
        return sorted(EXIT_ROLES)
    return sorted(number for number, role in EXIT_ROLES.items() if role in roles)

def portal_capabilities() -> dict:
    exits = _clearable_exits()
    roles = set(frappe.get_roles())
    return {
        "estate_read": _can("Building", "read"),
        "today": _can("Housing Assignment", "create", "submit")
        or _can("Housing Checkout", "create", "submit"),
        "count": _can("Housing Inventory", "read", "write"),
        "delivery_read": _can("Facility Asset Delivery", "read"),
        "clear_exit": _can("Facility Asset Delivery", "write"),
        "exits": exits,
        "clear_exit_1": 1 in exits,
        "clear_exit_3": 3 in exits,
        "confirm_delivery_receipt": _can("Facility Asset Delivery", "write")
        and bool({"System Manager", "Accommodation Manager", "Resident Supervisor"} & roles),
        "set_readiness": _can("Room", "write"),
        "check_in": _can("Housing Assignment", "create", "submit"),
        "check_out": _can("Housing Checkout", "create", "submit"),
        "custody_read": _can("Custody Issue", "read"),
        "issue_custody": _can("Custody Issue", "create", "submit"),
        "return_custody": _can("Custody Return", "create", "submit"),
        "register_worker": _can("Temporary Worker", "create"),
        "transfer": _can("Room Bed Transfer", "create", "submit"),
        "maintenance_read": _can("Maintenance Request", "read"),
        "maintenance_create": _can("Maintenance Request", "create"),
        "maintenance_work_order_action": False,
        "safety_draft": _can("Safety Task Execution", "create"),
        "safety_check": _can("Safety Task Execution", "submit"),
        "safety_read": _can("Safety Task Execution", "create")
        or _can("Safety Task Execution", "submit"),
    }

def portal_landing(capabilities: dict) -> str:
    if capabilities.get("estate_read") and capabilities.get("set_readiness"):
        return "/overview"
    if capabilities.get("check_in") or capabilities.get("check_out"):
        return "/today"
    if capabilities.get("delivery_read"):
        return "/delivery"
    if capabilities.get("safety_draft"):
        return "/rounds"
    return "/access-denied"

def bootstrap_portal_context(context, route: str):
    guest_redirect(route)

    allowed = bool(PORTAL_ROLES & set(frappe.get_roles()))
    capability_map = portal_capabilities() if allowed else {}
    capabilities = [
        name for name, granted in capability_map.items()
        if granted is True
    ]
    initial_route = "/rounds" if route == "/safety" else portal_landing(capability_map)
    return publish_portal_context(
        context,
        entry="housing",
        public_path=route,
        initial_route=initial_route,
        capabilities=capabilities,
        subject=frappe.session.user,
    )

def get_context(context):
    return bootstrap_portal_context(context, "/housing")
