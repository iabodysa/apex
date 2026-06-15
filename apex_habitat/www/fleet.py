"""Fleet OS — supervisor fleet dashboard served at /fleet.

Unlike the driver portal (/driver) and the worker app (/masar), this is an
ADMIN dashboard, not a guest-facing portal: it shows the whole fleet and drives
live operations on it. So it requires a logged-in user AND a fleet role.

Access gate:
  * Guests are redirected to /login (then back to /fleet).
  * A logged-in user without any fleet role gets a PermissionError — the page
    is not exposed to arbitrary users. The same Salis Vehicle / project scope
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

    # Require a fleet role; otherwise the page is not exposed.
    if not (FLEET_ROLES & set(frappe.get_roles())):
        raise frappe.PermissionError(frappe._("Not permitted to view the fleet dashboard."))

    context.no_cache = 1
    context.csrf_token = get_csrf_token()
    return context
