# Copyright (c) 2026, AFMCO and contributors
"""Masar Route Supervisor portal — served at /masar-supervisor.

The route supervisor is the person who dispatches buses: they approve the Route Plan
assigned to them, watch boarding fill up live, follow the ordered stops, and track the
driver on a map. Like the Fleet OS board (/fleet-os), this is an ADMIN portal, not a
guest-facing one — it requires a logged-in user holding a supervisor role. Every read the
SPA makes is additionally row-scoped server-side to the caller's OWN assigned plans
(route_supervisor == session user), so the role gate here is a coarse door, not the data
boundary.

Access gate:
  * Guests are redirected to /login (then back to /masar-supervisor).
  * A logged-in user without a supervisor role gets a friendly access page, not a raw 403.

The CSRF token is exposed (same pattern as fleet.py/driver.py) so the SPA's whitelisted
POSTs (approve / reject) pass Frappe's CSRF guard. no_cache is set because the page renders
per-user, live data.

Controller filename note: Frappe resolves a www page's controller by replacing hyphens
with underscores in the template basename (see TemplatePage.set_pymodule_path —
``template_basepath.replace("-", "_") + ".py"``). The template is ``masar-supervisor.html``
so its controller MUST be ``masar_supervisor.py`` (underscore); a hyphenated
``masar-supervisor.py`` is never imported, ``get_context`` never runs, and the page falls
through to the "no role" branch for EVERY user regardless of their actual roles.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import guest_redirect

# Roles that may open the supervisor portal (mirrors the API's PORTAL_ROLES).
SUPERVISOR_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile. Reuses the page's own SUPERVISOR_ROLES so
    the tile can never show for a user get_context() would turn away. Wired as the
    has_permission of the "apex-masar-supervisor" tile in hooks.py add_to_apps_screen."""
    return bool(SUPERVISOR_ROLES & set(frappe.get_roles()))


def get_context(context):
    guest_redirect("/masar-supervisor")

    context.no_cache = 1
    context.has_supervisor_role = bool(SUPERVISOR_ROLES & set(frappe.get_roles()))
    if context.has_supervisor_role:
        context.csrf_token = get_csrf_token()
        conf = frappe.get_site_config()
        context.site_name = frappe.local.site
        context.socketio_port = cint(conf.get("socketio_port")) or 9000
        context.async_enabled = not cint(conf.get("disable_async"))
        context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context
