"""Masar — standalone read-only "my worker route today" page (server-rendered).

A minimal self-contained surface, separate from the Vue driver portal: the
session user is resolved to a Salis Driver server-side and today's Workers-line
route (trips, ordered stops, registered manifest) is rendered as plain HTML.

Read-only — nothing here writes, posts GL, or commits. Guests are redirected to
login; an unlinked (non-driver) user gets a friendly message instead of a 403.
The CSRF token is exposed using the same pattern as the driver portal so any
later client-side read POST works behind Frappe's CSRF guard."""

import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.salis.api import masar
from apex_habitat.salis.api.driver_portal import _find_driver, _portal_enabled


def get_context(context):
	# Logged-in only; guests go to login and back.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/masar"
		raise frappe.Redirect

	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	context.today = frappe.utils.today()

	# Soft state for a friendly page (no 403): portal availability + driver link.
	context.portal_enabled = bool(_portal_enabled())
	driver = _find_driver()
	context.driver = driver
	context.route = None
	if context.portal_enabled and driver:
		# Reuse the whitelisted read endpoint's logic; it re-resolves the same
		# session user, so the page only ever shows the current driver's route.
		context.route = masar.get_my_worker_route_today()
	return context
