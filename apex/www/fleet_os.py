# Copyright (c) 2026, Apex contributors
"""Fleet operations supervisor board served at /fleet-os.

Controller shape follows fleet.py (same FLEET_ROLES constant, same CSRF + socket
bootstrap), but the GATES now differ: this board still requires a fleet role,
whereas /fleet dropped its role check and admits every logged-in user. Route,
redirect target and served bundle differ too. The route is hyphenated (/fleet-os
via www/fleet-os.html) while THIS module is underscored so it is importable — a
hyphenated .py never imports.

Route trace: hooks.py tile `apex-fleet-os` -> `www/fleet-os.html` -> generated
`apex_portal` shell -> `fleet-operations` feature.
"""

import frappe
from apex.apex_core.utils.portal_language import render_in_arabic
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context

FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile — same FLEET_ROLES check get_context()
    applies, so the tile never shows for a user the page turns away. Wired as the
    has_permission of the "apex-fleet-os" tile in hooks.py add_to_apps_screen."""
    return bool(FLEET_ROLES & set(frappe.get_roles()))


def get_context(context):
    """Redirects guests to login and bootstraps the fleet supervisor board, gated on a fleet role."""
    guest_redirect("/fleet-os")

    render_in_arabic()
    allowed = bool(FLEET_ROLES & set(frappe.get_roles())) and bool(
        frappe.has_permission("Salis Vehicle", "read")
    )
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
