from frappe.sessions import get_csrf_token

from apex_habitat.apex_core.utils.portal_bootstrap import (
	apply_portal_appearance,
	guest_redirect,
)


def get_context(context):
	# [#s5uw04]
	guest_redirect("/driver")
	context.no_cache = 1
	context.csrf_token = get_csrf_token()

	# [#l1s556]
	apply_portal_appearance(context)
	return context
