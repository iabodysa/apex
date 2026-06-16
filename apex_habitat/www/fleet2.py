"""Fleet OS preview (Vue rebuild) served at /fleet2.

Temporary side-by-side route: it renders the new `fleet_portal` Vue app so the
new board can be compared against the live raw `/fleet` page before the final
swap. Same access gate as fleet.py, with one planned improvement — a logged-in
user WITHOUT a fleet role gets a friendly in-page notice (rendered by
fleet2.html) instead of a raw 403. Guests are still redirected to login.

Once the rebuild is signed off, fleet.html/fleet.py adopt this shell + gate and
these fleet2.* files are removed.
"""

import frappe
from frappe.sessions import get_csrf_token

# Roles permitted to open the fleet dashboard (mirrors fleet.py).
FLEET_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def get_context(context):
    # Admin dashboard: require a logged-in user. Guests go to login and back.
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/fleet2"
        raise frappe.Redirect

    context.no_cache = 1
    # Friendly no-role page instead of a raw PermissionError: the template shows
    # the board only when the user holds a fleet role, otherwise a notice.
    context.has_fleet_role = bool(FLEET_ROLES & set(frappe.get_roles()))
    if context.has_fleet_role:
        context.csrf_token = get_csrf_token()
    return context
