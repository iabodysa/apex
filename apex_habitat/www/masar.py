"""Masar — worker self-service app shell (Vue SPA served at /masar).

Masar is the worker's mobile self-service app: a transported and housed Employee
opens their PERSONAL link (``/masar?w=<token>``) on a phone and manages their
profile, accommodation, transport, and requests. Workers are NOT Frappe users —
identity is the unguessable token, resolved server-side by the worker endpoints
(``apex_habitat.salis.api.masar``), which scope every query to one Employee.

This page is therefore Guest-accessible (no login redirect): it only serves the
built SPA shell and passes the token through to the client. The CSRF token is
exposed using ``frappe.sessions.get_csrf_token()`` (same pattern as the driver
portal) so the SPA's whitelisted calls work behind Frappe's CSRF guard. The
appearance (theme + optional brand overrides) reuses the Salis Portal Theme.

The old read-only "my worker route today" view that previously lived here has
moved into the driver portal (/driver → "My Route"); see
``apex_habitat.salis.api.driver_portal.my_worker_route_today``.
"""

import frappe
from frappe.sessions import get_csrf_token

from apex_habitat.salis.doctype.salis_portal_theme.salis_portal_theme import (
	get_portal_appearance,
)


def get_context(context):
	# [#88swmm]
	# [#qmqppr]
	context.no_cache = 1

	# [#sn2mtb]
	# [#atilnz]
	# [#w4wmsj]
	# [#mc35n2]
	# [#62mf34]
	try:
		context.csrf_token = get_csrf_token()
	except Exception:
		context.csrf_token = ""

	# [#ruhxyh]
	# [#o7gh0y]
	context.masar_token = frappe.form_dict.get("w") or ""

	appearance = get_portal_appearance()
	context.portal_theme = appearance["theme"]
	context.portal_accent = appearance["accent"]
	context.portal_logo = appearance["logo"]
	context.portal_show_brand = appearance["show_brand"]
	return context
