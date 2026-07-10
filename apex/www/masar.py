# Copyright (c) 2026, AFMCO and contributors
"""Masar — worker self-service app shell (Vue SPA served at /masar).

Masar is the worker's mobile self-service app: a transported and housed Employee
opens their PERSONAL link (``/masar?w=<token>``) on a phone and manages their
profile, accommodation, transport, and requests. Workers are NOT Frappe users —
identity is the unguessable token, resolved server-side by the worker endpoints
(``apex.salis.api.masar``), which scope every query to one Employee.

This page is therefore Guest-accessible (no login redirect): it only serves the
built SPA shell and passes the token through to the client. The CSRF token is
exposed using ``frappe.sessions.get_csrf_token()`` (same pattern as the driver
portal) so the SPA's whitelisted calls work behind Frappe's CSRF guard. The
appearance (theme + optional brand overrides) reuses the Salis Portal Theme.

The old read-only "my worker route today" view that previously lived here has
moved into the driver portal (/driver → "My Route"); see
``apex.salis.api.driver_portal.my_worker_route_today``.
"""

import re

import frappe
from frappe.sessions import get_csrf_token

from apex.apex_core.utils.portal_bootstrap import apply_portal_appearance

# [#wtk5x9] The personal token is minted by frappe.generate_hash (hex) — see
# apex_core/doctype/masar_worker_token. Accept only the url-safe charset that a
# real token can contain so a hostile ?w= payload (";</script>... etc.) is reduced
# to "" before it ever reaches the cookie/transport. Length-bounded so a junk query
# string can never become an oversized cookie.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# [#tokcookie] The personal token rides to the worker endpoints in this httpOnly,
# SameSite=Lax cookie (set once from the ?w= hit, scoped to /masar), NOT in the URL
# (T-685: out of access logs) and NOT inlined into the page HTML (T-705: a script
# variable any injected script could read). httpOnly means client JS cannot read it
# either, so an XSS on the shell cannot exfiltrate the worker's link.
MASAR_TOKEN_COOKIE = "masar_wt"
# Mirror the link TTL ceiling so the cookie never outlives the longest possible link.
_COOKIE_MAX_AGE_SECONDS = 180 * 24 * 60 * 60


def get_context(context):
	# [#kqaxzl]
	context.no_cache = 1

	# [#tokrefpol] T-660: the Referrer-Policy is set on the page itself via a
	# <meta name="referrer" content="no-referrer"> in masar.html — the www template
	# renderer builds its own Response and does not propagate a header set here, so a
	# meta tag is the renderer-independent guard. It stops the /masar?w=<token>
	# first-hit URL leaking to any third party via the Referer header before the
	# redirect strips the token from the URL bar.

	# [#ktvbza] get_csrf_token() mints+returns a token for Guest too (it generates
	# one if the session has none), so it does not legitimately fail here. The old
	# blanket `except: csrf_token = ""` only ever produced a silently-empty token
	# that made every Masar POST fail CSRF with no trace — let a real failure surface
	# and be logged instead of swallowing the token.
	context.csrf_token = get_csrf_token()

	# [#tokcookie] Token handoff: a freshly distributed /masar?w=<token> link arrives
	# with the token in the query string ONCE. We charset-validate it, drop it into
	# the httpOnly cookie, and (when the cookie was just set) redirect to a CLEAN
	# /masar so the secret is stripped from the URL bar / browser history / WhatsApp
	# residue (T-660). Thereafter the SPA carries no token at all — the endpoints read
	# the cookie server-side. The page therefore inlines NO raw token (T-705); only a
	# boolean telling the shell whether a link is present.
	raw_token = frappe.form_dict.get("w") or ""
	valid_token = raw_token if _TOKEN_RE.match(raw_token) else ""
	if valid_token:
		_set_token_cookie(valid_token)
		# Strip ?w= from the URL and reload from the cookie. The cookie is flushed on
		# this redirect response, so the clean reload carries it.
		frappe.local.flags.redirect_location = "/masar"
		raise frappe.Redirect

	# No ?w= on this request: a link is present iff the httpOnly cookie is set. The
	# raw value is never exposed to the client — only this presence flag.
	context.masar_has_token = bool(_request_token_cookie())

	# [#9tqm2e] accent/logo come from the (now validate()-guarded) Salis Portal
	# Theme. They are emitted JS-safe via tojson (script) / colour-validated at the
	# source (the <style> accent); not pre-escaped here to avoid double-encoding.
	apply_portal_appearance(context)
	return context


def _set_token_cookie(token: str) -> None:
	"""Persist the validated token in the httpOnly /masar cookie (best-effort).

	Guarded so a missing cookie_manager (e.g. a non-request render path) degrades to
	leaving the query-string token in place rather than 500-ing the page."""
	cm = getattr(frappe.local, "cookie_manager", None)
	if cm is None:
		return
	cm.set_cookie(
		MASAR_TOKEN_COOKIE,
		token,
		httponly=True,
		samesite="Lax",
		max_age=_COOKIE_MAX_AGE_SECONDS,
	)


def _request_token_cookie() -> str:
	"""The token already stored in the request's httpOnly cookie, or ''."""
	request = getattr(frappe.local, "request", None)
	if request is None:
		return ""
	try:
		return (request.cookies.get(MASAR_TOKEN_COOKIE) or "").strip()
	except Exception:
		return ""
