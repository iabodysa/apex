import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex_habitat.apex_core.utils.portal_bootstrap import (
	apply_portal_appearance,
	guest_redirect,
)


def get_context(context):
	# [#s5uw04]
	guest_redirect("/driver")
	context.no_cache = 1
	context.csrf_token = get_csrf_token()

	# Socket.IO config so the SPA can subscribe to live driver_trip_update pushes.
	# async disabled -> the page falls back to its manual fetch (the flag tells it).
	# site_name is the socket namespace (mirrors frappe.boot.sitename).
	conf = frappe.get_site_config()
	context.site_name = frappe.local.site
	context.socketio_port = cint(conf.get("socketio_port")) or 9000
	context.async_enabled = not cint(conf.get("disable_async"))

	# [#l1s556]
	apply_portal_appearance(context)
	return context
