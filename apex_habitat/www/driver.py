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
	# In dev (developer_mode, no nginx) the SPA must hit host:socketio_port directly;
	# in prod nginx proxies /socket.io/ on the origin. window.dev_server is Desk-only,
	# so a www page must carry the flag itself.
	context.dev_server = 1 if frappe.conf.developer_mode else 0

	# [#l1s556]
	apply_portal_appearance(context)
	return context
