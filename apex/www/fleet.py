# Copyright (c) 2026, Apex contributors
"""Fleet representative self-service page served at /fleet.

The signed-in representative sees their vehicle, fuel, incidents, and complaints.
Fleet operations use `/fleet-os` in the same Vue application.

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
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context
from apex.salis.api.fleet_employee import get_context as get_fleet_context

FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def has_apps_screen_access() -> bool:
    """retained-unused: /fleet is ungated by design, so no tile points here.

    The "apex-fleet" tile in hooks.py add_to_apps_screen carries NO has_permission
    key, so Frappe never calls this. That is deliberate, not a missing wire. The
    /apps tile gate exists to MIRROR a page's own gate — README's contract is that
    a tile "can never be shown to a user the page would turn away" — and
    get_context() below turns nobody away: every logged-in user gets can_view = 1,
    with per-user scoping enforced server-side by the fleet_employee endpoints.
    Gating the tile on FLEET_ROLES would invert that contract, hiding "My Fleet"
    from the ordinary employees the page exists to serve. The sibling open worker
    pages /driver and /masar match this shape: no helper, no has_permission.

    Kept rather than deleted so the fleet role-set stays documented beside the page
    and the gate is one hooks line away should /fleet ever become role-restricted.
    Contrast www/fleet_os.py, whose identical helper IS wired to "apex-fleet-os".
    """
    return bool(FLEET_ROLES & set(frappe.get_roles()))


def get_context(context):
    """Redirects guests to login and bootstraps the fleet self-service page for any logged-in user."""
    guest_redirect("/fleet")

    fleet_context = get_fleet_context()
    grants = ["fleet.self.read"]
    for key in ("handover", "fuel", "incident", "complaint"):
        if fleet_context.get("capabilities", {}).get(key):
            grants.append(f"fleet.self.{key}")
    return publish_portal_context(
        context,
        entry="fleet-self-service",
        public_path="/fleet",
        initial_route="/",
        capabilities=grants,
        subject=frappe.session.user,
    )
