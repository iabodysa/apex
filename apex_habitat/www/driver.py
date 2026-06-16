import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.salis.doctype.salis_portal_theme.salis_portal_theme import (
	get_portal_appearance,
)


def get_context(context):
	# [#s5uw04]
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/driver"
		raise frappe.Redirect
	context.no_cache = 1
	context.csrf_token = get_csrf_token()

	# [#l1s556]
	appearance = get_portal_appearance()
	context.portal_theme = appearance["theme"]
	context.portal_accent = appearance["accent"]
	context.portal_logo = appearance["logo"]
	context.portal_show_brand = appearance["show_brand"]
	return context
