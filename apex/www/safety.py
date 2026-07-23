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

from apex.apex_core.utils.portal_bootstrap import (
    apply_portal_appearance,
    guest_redirect,
)

# [#pzzvqb]
SAFETY_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
}


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile (A-024) — same SAFETY_ROLES check
    get_context() applies, so the tile never shows for a user the page itself
    would turn away."""
    return bool(SAFETY_ROLES & set(frappe.get_roles()))


def get_context(context):
    guest_redirect("/safety")

    context.no_cache = 1
    context.has_safety_role = bool(SAFETY_ROLES & set(frappe.get_roles()))
    if context.has_safety_role:
        context.csrf_token = get_csrf_token()
        # [#t6z4ul]
        apply_portal_appearance(context)
        # [#3ujvm8]
        conf = frappe.get_site_config()
        context.site_name = frappe.local.site
        context.socketio_port = cint(conf.get("socketio_port")) or 9000
        context.async_enabled = not cint(conf.get("disable_async"))
        # [#eovfvf]
        context.dev_server = 1 if frappe.conf.developer_mode else 0
    return context
