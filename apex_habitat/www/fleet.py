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

# Roles permitted to open the fleet dashboard.
FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def get_context(context):
    # Admin dashboard: require a logged-in user. Guests go to login and back.
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/fleet"
        raise frappe.Redirect

    context.no_cache = 1
    # Friendly no-role page instead of a raw PermissionError: the template shows
    # the board only when the user holds a fleet role, otherwise a notice.
    context.has_fleet_role = bool(FLEET_ROLES & set(frappe.get_roles()))
    if context.has_fleet_role:
        context.csrf_token = get_csrf_token()
    return context
