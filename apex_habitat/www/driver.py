import frappe
from frappe.sessions import get_csrf_token


def get_context(context):
	# Driver portal requires a logged-in user; guests are sent to login.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/driver"
		raise frappe.Redirect
	context.no_cache = 1
	context.csrf_token = get_csrf_token()
	return context
