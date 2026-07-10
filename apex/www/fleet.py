# Copyright (c) 2026, AFMCO and contributors
"""Fleet OS — supervisor fleet dashboard served at /fleet.

Unlike the driver portal (/driver) and the worker app (/masar), this is an
ADMIN dashboard, not a guest-facing portal: it shows the whole fleet and drives
live operations on it. So it requires a logged-in user AND a fleet role.

Access gate:
  * Guests are redirected to /login (then back to /fleet).
  * A logged-in user without any fleet role gets a friendly "fleet role
    required" page (not a raw 403). The same Salis Vehicle / project scope
    that the API enforces still applies to every read and write the page makes.

The CSRF token is exposed (same pattern as driver.py) so the single-page app's
whitelisted POSTs (reassign / stop / theft / workshop / recover) pass Frappe's
CSRF guard. no_cache is set because the page renders per-user, live data.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import guest_redirect

# [#i6khen]
FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def get_context(context):
    # [#nyktq0]
    guest_redirect("/fleet")

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
