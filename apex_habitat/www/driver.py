import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.salis.doctype.salis_portal_theme.salis_portal_theme import (
	get_portal_appearance,
)


def get_context(context):
	# Driver portal requires a logged-in user; guests are sent to login.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/driver"
		raise frappe.Redirect
	context.no_cache = 1
	context.csrf_token = get_csrf_token()

	# Portal appearance (theme + optional brand overrides) drives the design-token
	# stylesheet via a `data-theme` attribute and an inline `--c-accent` override.
	# get_portal_appearance() always returns safe defaults (flat AFMCO theme,
	# branding on) so the page renders even before the Single is configured.
	appearance = get_portal_appearance()
	context.portal_theme = appearance["theme"]
	context.portal_accent = appearance["accent"]
	context.portal_logo = appearance["logo"]
	context.portal_show_brand = appearance["show_brand"]
	return context
