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

import re

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import escape_html

from apex_habitat.apex_core.utils.portal_bootstrap import apply_portal_appearance

# [#wtk5x9] The personal token is minted by frappe.generate_hash (hex) — see
# apex_core/doctype/masar_worker_token. Accept only the url-safe charset that a
# real token can contain so a hostile ?w= payload (";</script>... etc.) is reduced
# to "" before it ever reaches the inline <script>. Belt: the template also emits
# it via tojson (the www renderer has autoescape OFF, so a bare "{{ }}" in a
# <script> is a raw-injection sink).
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def get_context(context):
	# [#kqaxzl]
	context.no_cache = 1

	# [#ktvbza] get_csrf_token() mints+returns a token for Guest too (it generates
	# one if the session has none), so it does not legitimately fail here. The old
	# blanket `except: csrf_token = ""` only ever produced a silently-empty token
	# that made every Masar POST fail CSRF with no trace — let a real failure surface
	# and be logged instead of swallowing the token.
	context.csrf_token = get_csrf_token()

	# [#tvmj3m] Charset-validate then HTML-escape the request-supplied token. The
	# value is forwarded verbatim to the SPA, which resolves it server-side; only
	# the url-safe token charset is ever legitimate, so anything else (an XSS
	# payload) is dropped to "". escape_html is a no-op for that charset (no double
	# encoding) but keeps the source belt alongside the template's tojson emission.
	raw_token = frappe.form_dict.get("w") or ""
	context.masar_token = escape_html(raw_token) if _TOKEN_RE.match(raw_token) else ""

	# [#9tqm2e] accent/logo come from the (now validate()-guarded) Salis Portal
	# Theme. They are emitted JS-safe via tojson (script) / colour-validated at the
	# source (the <style> accent); not pre-escaped here to avoid double-encoding.
	apply_portal_appearance(context)
	return context
