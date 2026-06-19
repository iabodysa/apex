"""Safety Rounds portal served at /safety.

A mobile-first supervisor surface for the Safety Checklist (T-289): pick a
building, see the cadences that are DUE now, tap each task Pass/Fail/Issue, then
submit one round per cadence and email the manager. Like /fleet this is an
admin-style portal, not a guest link, so it requires a logged-in user AND a
safety role.

Access gate (mirrors www/fleet.py):
  * Guests are redirected to /login (then back to /safety).
  * A logged-in user without any safety role gets a friendly "role required"
    page, not a raw 403. The same permissions the API enforces still apply to
    every read and write the page makes.

The CSRF token is exposed (same pattern as fleet.py) so the single-page app's
whitelisted POSTs (submit_due_rounds) pass Frappe's CSRF guard. no_cache is set
because the page renders per-user, live data.
"""

import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.salis.doctype.salis_portal_theme.salis_portal_theme import (
    get_portal_appearance,
)

# Roles allowed to run safety rounds from the portal. Matches the submit-capable
# roles the safety_checklist API gates on (Safety Officer is intentionally
# excluded: it cannot submit a Safety Round).
SAFETY_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/safety"
        raise frappe.Redirect

    context.no_cache = 1
    context.has_safety_role = bool(SAFETY_ROLES & set(frappe.get_roles()))
    if context.has_safety_role:
        context.csrf_token = get_csrf_token()
        # Appearance (theme + optional brand overrides) from the Salis Portal
        # Theme — same projection as www/driver.py so /safety re-skins with the
        # other portals. Only set for the authorised view.
        appearance = get_portal_appearance()
        context.portal_theme = appearance["theme"]
        context.portal_accent = appearance["accent"]
        context.portal_logo = appearance["logo"]
        context.portal_show_brand = appearance["show_brand"]
    return context
