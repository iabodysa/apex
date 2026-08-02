# Copyright (c) 2026, AFMCO and contributors
"""Masar Route Supervisor portal — served at /masar-supervisor.

The route supervisor is the person who dispatches buses: they approve the Route Plan
assigned to them, watch boarding fill up live, follow the ordered stops, and track the
driver on a map. Like the Fleet OS board (/fleet-os), this is an ADMIN portal, not a
guest-facing one — it requires a logged-in user holding a supervisor role. Every read the
SPA makes is additionally row-scoped server-side to the caller's OWN assigned plans
(route_supervisor == session user), so the role gate here is a coarse door, not the data
boundary.

Access gate:
  * Guests are redirected to /login (then back to /masar-supervisor).
  * A logged-in user without a supervisor role gets a friendly access page, not a raw 403.

The CSRF token is exposed (same pattern as fleet.py/driver.py) so the SPA's whitelisted
POSTs (approve / reject) pass Frappe's CSRF guard. no_cache is set because the page renders
per-user, live data.

Controller filename note: Frappe resolves a www page's controller by replacing hyphens
with underscores in the template basename (see TemplatePage.set_pymodule_path —
``template_basepath.replace("-", "_") + ".py"``). The template is ``masar-supervisor.html``
so its controller MUST be ``masar_supervisor.py`` (underscore); a hyphenated
``masar-supervisor.py`` is never imported, ``get_context`` never runs, and the page falls
through to the "no role" branch for EVERY user regardless of their actual roles.

Map tile source — ACCEPTED THIRD-PARTY FETCH (2026-07-25)
The live driver map draws its background from tile.openstreetmap.org by default. That
is a deliberate, recorded acceptance, not an oversight: self-hosting or rendering a tile
pyramid is disproportionate for one supervisor panel, and the executable-code risk that
forced Leaflet itself to be vendored does not apply here — a tile is a PNG image, not a
script, so nothing third-party executes with the supervisor's session.

What a tile request discloses, precisely:
  * the tile path ``/{z}/{x}/{y}.png`` — the map's approximate viewport at tile
    resolution. The map re-centres on the tracked driver, so this is approximately where
    an AFMCO vehicle is, to roughly a city block at the zoom levels used;
  * timing — one burst per pan/zoom, and the position poll runs every 10s while the map
    tab is open and visible, so the request stream also reveals WHEN a trip is being
    watched and that the vehicle is moving;
  * ordinary HTTP metadata — the browser's public IP and User-Agent, plus the site's
    ORIGIN as Referer (the default strict-origin-when-cross-origin policy trims the path,
    so ``/masar-supervisor`` itself is not sent).

What it does NOT disclose: no cookie or CSRF token crosses the boundary (a plain
cross-origin image request carries no credentials), and no employee name, plate, trip id,
Route Plan or any other Frappe record appears anywhere in a tile URL. The requests do
originate from an authenticated supervisor session, so the coordinates are attributable
to this deployment even though no identity is transmitted.

Degradation: the map is never load-bearing. Leaflet missing → a plain coordinate readout;
tile host unreachable → the driver marker, the live badge, the driver/vehicle strip and
every other tab still render over a blank canvas, with a note that the background is
unavailable. Asserted in DriverMap.vue.

A deployment that needs a contracted or self-hosted tile source sets ``apex_map_tile_url``
(and optionally ``apex_map_tile_attribution``) in site_config.json — no code change. The
value must be https:// or a root-relative path; anything else is ignored so a
misconfiguration cannot silently downgrade an https page into blocked mixed content.
"""

import frappe
from frappe.sessions import get_csrf_token
from frappe.utils import cint

from apex.apex_core.utils.portal_bootstrap import guest_redirect

# Roles that may open the supervisor portal (mirrors the API's PORTAL_ROLES).
SUPERVISOR_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
}


def map_tile_override(conf) -> dict:
    """Site-config tile source, or empty to keep the component's OpenStreetMap default.
    Rejects anything that is not https:// or root-relative — see the module docstring."""
    url = str(conf.get("apex_map_tile_url") or "").strip()
    # "//host/..." is protocol-relative, i.e. off-site, not root-relative.
    root_relative = url.startswith("/") and not url.startswith("//")
    if not (url.startswith("https://") or root_relative):
        return {"url": "", "attribution": ""}
    return {"url": url, "attribution": str(conf.get("apex_map_tile_attribution") or "").strip()}


def has_apps_screen_access() -> bool:
    """Gate for the /apps app-selector tile. Reuses the page's own SUPERVISOR_ROLES so
    the tile can never show for a user get_context() would turn away. Wired as the
    has_permission of the "apex-masar-supervisor" tile in hooks.py add_to_apps_screen."""
    return bool(SUPERVISOR_ROLES & set(frappe.get_roles()))


def get_context(context):
    guest_redirect("/masar-supervisor")

    context.no_cache = 1
    context.has_supervisor_role = bool(SUPERVISOR_ROLES & set(frappe.get_roles()))
    if context.has_supervisor_role:
        context.csrf_token = get_csrf_token()
        conf = frappe.get_site_config()
        context.site_name = frappe.local.site
        context.socketio_port = cint(conf.get("socketio_port")) or 9000
        context.async_enabled = not cint(conf.get("disable_async"))
        context.dev_server = 1 if frappe.conf.developer_mode else 0
        context.map_tiles = map_tile_override(conf)
    return context
