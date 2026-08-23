# Copyright (c) 2026, Apex contributors
"""Authenticated Masar supervisor portal at ``/masar-supervisor``."""

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
    """Gate for the /apps app-selector tile. Reuses the page's own SUPERVISOR_ROLES so
    the tile can never show for a user get_context() would turn away. Wired as the
    has_permission of the "apex-masar-supervisor" tile in hooks.py add_to_apps_screen."""
    return bool(SUPERVISOR_ROLES & set(frappe.get_roles()))


def get_context(context):
    """Redirects guests to login and bootstraps the route supervisor portal, gated on a role."""
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
