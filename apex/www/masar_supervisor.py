# Copyright (c) 2026, Apex contributors

import frappe
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context

SUPERVISOR_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}
SUPERVISOR_CAPABILITIES = (
    "transport.request.read",
    "transport.assignment.read",
    "transport.trip.read",
    "transport.trip.location.read",
    "transport.history.read",
)


def has_apps_screen_access() -> bool:
    return bool(SUPERVISOR_ROLES & set(frappe.get_roles()))


def get_context(context):
    guest_redirect("/masar-supervisor")

    frappe.local.lang = "ar"
    allowed = bool(SUPERVISOR_ROLES & set(frappe.get_roles()))
    return publish_portal_context(
        context,
        entry="transport-supervisor",
        public_path="/masar-supervisor",
        initial_route="/requests",
        capabilities=SUPERVISOR_CAPABILITIES if allowed else (),
        subject=frappe.session.user,
    )
