# Copyright (c) 2026, AFMCO and contributors
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
from frappe.utils import cint

from apex_habitat.apex_core.utils.portal_bootstrap import (
    apply_portal_appearance,
    guest_redirect,
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
    guest_redirect("/safety")

    context.no_cache = 1
    context.has_safety_role = bool(SAFETY_ROLES & set(frappe.get_roles()))
    if context.has_safety_role:
        context.csrf_token = get_csrf_token()
        # Appearance only for the authorised view (same projection as the other
        # portals so /safety re-skins with them).
        apply_portal_appearance(context)
        # Socket.IO config so the SPA can subscribe to live safety_update pushes
        # (mirrors www/fleet.py). async disabled -> the page falls back to its
        # own fetch (the flag tells it). site_name is the socket namespace.
        conf = frappe.get_site_config()
        context.site_name = frappe.local.site
        context.socketio_port = cint(conf.get("socketio_port")) or 9000
        context.async_enabled = not cint(conf.get("disable_async"))
        # In dev (developer_mode, no nginx) the SPA must hit host:socketio_port
        # directly; in prod nginx proxies /socket.io/ on the origin. window.dev_server
        # is Desk-only, so a www page must carry the flag itself.
        context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context
