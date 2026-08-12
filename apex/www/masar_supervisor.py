# Copyright (c) 2026, Apex contributors
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

The live map loads the vendored Leaflet runtime and uses OpenStreetMap raster tiles.
Only tile coordinates and ordinary browser request metadata leave the site; no Frappe
cookie, token, employee name, plate number, or document identifier is sent. The route
list remains visible when the background tiles cannot load.
"""

import frappe
from apex.apex_core.utils.portal_language import render_in_arabic
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context

SUPERVISOR_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}
SUPERVISOR_CAPABILITIES = (
    "transport.request.read",
    "transport.shift.read",
    "transport.plan.read",
    "transport.plan.create",
    "transport.trip.read",
    "transport.trip.dispatch",
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

    render_in_arabic()
    allowed = bool(SUPERVISOR_ROLES & set(frappe.get_roles()))
    return publish_portal_context(
        context,
        entry="transport-supervisor",
        public_path="/masar-supervisor",
        initial_route="/requests",
        capabilities=SUPERVISOR_CAPABILITIES if allowed else (),
        subject=frappe.session.user,
    )
