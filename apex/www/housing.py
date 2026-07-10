# Copyright (c) 2026, AFMCO and contributors
"""Unified Housing portal served at /housing.

One mobile-first admin surface for TWO housing flows: the periodic Housing
Inventory count (formerly /housing-count) and the three-exit Facility Asset
Delivery clearance. Like /safety and /fleet this is an admin-style portal, not a
guest link, so it requires a logged-in user AND a housing role.

Access gate (mirrors www/safety.py, minus the realtime socket config — the
housing surface has no live push):
  * Guests are redirected to /login (then back to /housing).
  * A logged-in user without any housing role gets a friendly "role required"
    page, not a raw 403. The same permissions the count and delivery APIs
    enforce still apply to every read and write the page makes — the building
    scope confines a supervisor to their own estate.

HOUSING_ROLES is the UNION of the two flows' write roles:
  * count (habitat/api/housing_count.py submit_counts): System Manager,
    Accommodation Manager, Resident Supervisor;
  * delivery exits (habitat/api/facility_asset_delivery.py): Resident
    Supervisor (exit 1), Accommodation Manager (exit 2), Procurement Supervisor
    (exit 3), System Manager override.

The CSRF token is exposed (same pattern as safety.py) so the SPA's whitelisted
POSTs (submit_counts / pass_exit_* / confirm_receipt) pass Frappe's CSRF guard.
no_cache is set because the page renders per-user, live data.
"""

import frappe
from frappe.sessions import get_csrf_token

from apex.apex_core.utils.portal_bootstrap import (
	apply_portal_appearance,
	guest_redirect,
)

# Union of the count and delivery write roles (see module docstring).
HOUSING_ROLES = {
	"System Manager",
	"Accommodation Manager",
	"Resident Supervisor",
	"Procurement Supervisor",
}


def get_context(context):
	guest_redirect("/housing")

	context.no_cache = 1
	context.has_housing_role = bool(HOUSING_ROLES & set(frappe.get_roles()))
	if context.has_housing_role:
		context.csrf_token = get_csrf_token()
		# Appearance only for the authorised view (same projection as the other
		# portals so /housing re-skins with them).
		apply_portal_appearance(context)
	return context
