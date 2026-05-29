import frappe
from frappe.sessions import get_csrf_token


def get_context(context):
	# Driver portal requires a logged-in user; guests are sent to login.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/driver"
		raise frappe.Redirect
	context.no_cache = 1
	# The session CSRF token lives at frappe.session.data.csrf_token and is
	# generated lazily; get_csrf_token() creates it if needed and returns the
	# exact value auth.validate_csrf_token() checks POSTs against. The previous
	# frappe.session.csrf_token was always empty, so the SPA sent no token and
	# every logged-in POST failed with CSRFTokenError.
	context.csrf_token = get_csrf_token()
	return context
