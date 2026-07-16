# Copyright (c) 2026, AFMCO and contributors
"""Fleet OS supervisor board — preserved BACKUP served at /fleet-os.

This is the untouched supervisor dashboard that used to live at /fleet. When
/fleet became the employee self-service page, the full board was kept alive here
as a fallback (bundle: fleet_os_portal) until the owner decides to retire it.

Controller/route wiring mirrors fleet.py exactly (same FLEET_ROLES gate, same
CSRF + socket bootstrap), the only differences being the redirect target and the
served bundle. The route is hyphenated (/fleet-os via www/fleet-os.html) while
THIS module is underscored so it is importable — a hyphenated .py never imports.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import guest_redirect

# [#i6khen] Same role-set as the primary board — the backup gates identically.
FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def has_apps_screen_access() -> bool:
    """Gate for an optional /apps app-selector tile — same FLEET_ROLES check
    get_context() applies, so the tile never shows for a user the page turns
    away. (Not wired into add_to_apps_screen; kept for parity with fleet.py.)"""
    return bool(FLEET_ROLES & set(frappe.get_roles()))


def get_context(context):
    # [#nyktq0]
    guest_redirect("/fleet-os")

    context.no_cache = 1
    # [#4h1dwk]
    context.has_fleet_role = bool(FLEET_ROLES & set(frappe.get_roles()))
    if context.has_fleet_role:
        # [#qowj7c]
        context.fleet_caps = {"driver_lens": context.has_fleet_role}
        context.csrf_token = get_csrf_token()
        # [#6xr27k]
        conf = frappe.get_site_config()
        context.site_name = frappe.local.site
        context.socketio_port = cint(conf.get("socketio_port")) or 9000
        context.async_enabled = not cint(conf.get("disable_async"))
        # [#eovfvf]
        context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context
