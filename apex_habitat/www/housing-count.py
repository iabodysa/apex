# Copyright (c) 2026, AFMCO and contributors
"""Housing Inventory count portal served at /housing-count.

A mobile-first field surface (T-684) for the periodic Housing Inventory count:
pick a building, see its inventory lines grouped by room, count each line, set
its condition, then submit. Like /safety this is an admin-style portal, not a
guest link, so it requires a logged-in user AND a count-capable role.

Access gate (mirrors www/safety.py, minus the realtime socket config — the count
surface has no live push):
  * Guests are redirected to /login (then back to /housing-count).
  * A logged-in user without a count role gets a friendly "role required" page,
    not a raw 403. The same permissions the API enforces still apply to every
    read and write the page makes — the building scope confines a supervisor to
    their own estate's items.

The CSRF token is exposed (same pattern as safety.py) so the single-page app's
whitelisted POST (submit_counts) passes Frappe's CSRF guard. no_cache is set
because the page renders per-user, live data.
"""

import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.apex_core.utils.portal_bootstrap import (
    apply_portal_appearance,
    guest_redirect,
)

# Roles allowed to record an inventory count from the portal. Matches the
# write-capable Housing Inventory DocPerms (Resident Supervisor is now granted a
# building-scoped write so field-counting works).
COUNT_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
}


def get_context(context):
    guest_redirect("/housing-count")

    context.no_cache = 1
    context.has_count_role = bool(COUNT_ROLES & set(frappe.get_roles()))
    if context.has_count_role:
        context.csrf_token = get_csrf_token()
        # Appearance only for the authorised view (same projection as the other
        # portals so /housing-count re-skins with them).
        apply_portal_appearance(context)
    return context
