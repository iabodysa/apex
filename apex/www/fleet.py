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
