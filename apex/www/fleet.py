# Copyright (c) 2026, AFMCO and contributors
"""Fleet employee self-service page served at /fleet.

This is the EMPLOYEE page (my vehicle · fuel request · my recent trips), open to
any logged-in user. The old supervisor board that used to live here is preserved
untouched at /fleet-os (module fleet_os, bundle fleet_os_portal).

Access gate:
  * Guests are redirected to /login (then back to /fleet).
  * Every logged-in user may open the page — no fleet role is required. The data
    is scoped PER-USER on the server: apex.salis.api.fleet_employee resolves the
    session user to their own Salis Driver and returns only their vehicle / trips
    / fuel requests, so a user never sees another user's data. A user with no
    fleet vehicle simply gets the page's empty state.

The CSRF token is exposed (same pattern as driver.py) so the page's whitelisted
POST (submit_fuel_request) passes Frappe's CSRF guard. no_cache is set because
the page renders per-user, live data.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import guest_redirect

# [#i6khen] Retained for the /apps app-selector tile gate below — the employee
# page itself no longer gates on a role.
FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile (A-024). The fleet team gets the tile
    to their surface; ordinary employees reach /fleet directly, not via the tile."""
    return bool(FLEET_ROLES & set(frappe.get_roles()))


def get_context(context):
    # [#nyktq0]
    guest_redirect("/fleet")

    context.no_cache = 1
    # [#4h1dwk] Any logged-in user may view the employee page; per-user data
    # scoping is enforced server-side by the fleet_employee endpoints.
    context.can_view = 1
    context.csrf_token = get_csrf_token()
    # [#6xr27k]
    conf = frappe.get_site_config()
    context.site_name = frappe.local.site
    context.socketio_port = cint(conf.get("socketio_port")) or 9000
    context.async_enabled = not cint(conf.get("disable_async"))
    # [#eovfvf]
    context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context
