# Copyright (c) 2026, Apex contributors

import frappe
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context

FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def _may_view() -> bool:
    return bool(FLEET_ROLES & set(frappe.get_roles())) and bool(
        frappe.has_permission("Salis Vehicle", "read")
    )


def has_apps_screen_access() -> bool:
    return _may_view()


def get_context(context):
    guest_redirect("/fleet-os")

    allowed = _may_view()
    grants = ["fleet.operations.read"] if allowed else []
    if allowed and frappe.has_permission("Fuel Request", "write"):
        grants.append("fleet.operations.fuel")
    return publish_portal_context(
        context,
        entry="fleet-operations",
        public_path="/fleet-os",
        initial_route="/",
        capabilities=grants,
        subject=frappe.session.user,
    )
