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
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context

FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def _may_view() -> bool:
    """A fleet role plus live read on Salis Vehicle — the one gate both the /apps tile
    and get_context() apply, so a Role Permission Manager edit to Salis Vehicle can
    never leave the tile advertising a board the page then refuses."""
    return bool(FLEET_ROLES & set(frappe.get_roles())) and bool(
        frappe.has_permission("Salis Vehicle", "read")
    )


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile — same check get_context() applies, so the
    tile never shows for a user the page turns away. Wired as the has_permission of the
    "apex-fleet-os" tile in hooks.py add_to_apps_screen."""
    return _may_view()


def get_context(context):
    """Redirects guests to login and bootstraps the fleet supervisor board, gated on a fleet role."""
    guest_redirect("/fleet-os")

    frappe.local.lang = "ar"
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
