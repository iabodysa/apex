# Copyright (c) 2026, AFMCO and contributors
"""No portal page under apex/www/ may pull an executable asset from a CDN.

/masar-supervisor used to load leaflet@1.9.4 from unpkg.com. That put a runtime
dependency of an AUTHENTICATED page outside the npm manifest, outside the single
frontend/package-lock.json, and outside the dompurify/ws security overrides — an
unpinned third-party script that executes with the supervisor's session, plus a
hard failure on an offline or egress-filtered bench. Leaflet is now vendored at
apex/public/vendor/leaflet-<version>/ and pinned in frontend/package.json.

Every shell also linked Google Fonts. That shipped no executable code and each page
named a local fallback, so it degraded cosmetically rather than failing — but it was
still an unpinned third-party request from an AUTHENTICATED page, one hit per page
load, and on /masar the page carries a personal access token. The font hosts were
held OUT of CDN_HOSTS on purpose while that was true, so the gap could not silently
false-green. Cairo, Montserrat and JetBrains Mono are now vendored under
apex/public/vendor/<family>-<version>/ and the hosts are in the list below, which is
what closes it.

Five invariants are pinned here:

  1. No <script src> under apex/www/ points off-site. Third-party executable code
     on a logged-in page is the security case; this is the hard rule.
  2. No known package/script or font CDN host appears anywhere under apex/www/ —
     including in a preconnect, which opens the third-party connection on its own
     even when no stylesheet is ever fetched from it.
  3. /masar-supervisor references the vendored leaflet that actually exists on disk,
     so "no CDN" cannot be satisfied by pointing the page at a 404.
  4. Every vendored font stylesheet a shell links exists on disk, resolves its own
     woff2 files, and keeps font-display: swap — losing swap would change first paint.
  5. No CDN host appears in a portal SPA's source under frontend/*/src/ or in its BUILT
     bundle under apex/public/*_portal/. Both sides are checked: the source so a
     regression is caught at review, the committed bundle so a stale build cannot pass
     on the strength of a source that was already fixed.
"""

import re
import unittest
from pathlib import Path

import apex
from apex.tests.source_tree import CDN_HOSTS

APP_ROOT = Path(apex.__file__).resolve().parent
WWW_DIR = APP_ROOT / "www"
PUBLIC_DIR = APP_ROOT / "public"

# src on a <script>, whether quoted with ' or ". Protocol-relative //host counts as
# off-site too, which is why the scheme is optional in the URL test below.
SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
OFFSITE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)

# Every apex/www/*.html is now a 63-byte include of this one file — the portals
# converged on a single Frappe-UI application — so the "shell" this guard talks about is
# here, not under www/. The old LEAFLET_* and MOUNT_NODE/BUNDLE_SCRIPT constants went with
# the cases that used them.
SHARED_SHELL = APP_ROOT / "templates" / "includes" / "apex_portal_app.html"

VENDOR_PREFIX = "/assets/apex/vendor/"
# A stylesheet href pointing into the vendored asset tree.
VENDOR_CSS_HREF = re.compile(
    rf"<link\b[^>]*\bhref\s*=\s*[\"']({re.escape(VENDOR_PREFIX)}[^\"']+\.css)[\"']",
    re.IGNORECASE,
)
FONT_FACE_SRC = re.compile(r"src\s*:\s*url\(\s*[\"']?([^\"')]+)[\"']?\s*\)")
FONT_DISPLAY = re.compile(r"font-display\s*:\s*([a-z-]+)\s*;", re.IGNORECASE)
# An actual rule, not the words "@font-face" in a comment.
FONT_FACE_RULE = re.compile(r"@font-face\s*\{(.*?)\}", re.DOTALL | re.IGNORECASE)

# Suffixes a browser can receive from apex/www. Anything not listed here must be
# classified below, so a new asset type cannot escape the scan by omission.
SERVABLE_SUFFIXES = frozenset({".html", ".md", ".js", ".css", ".json", ".svg", ".txt"})
# Server-side only: TemplatePage.can_render refuses a Python suffix outright
# (template_page.py:70-75), so these bytes never leave the server. .pyc/.pyo are
# the __pycache__ artefacts a local test run leaves behind.
NON_SERVABLE_SUFFIXES = frozenset({".py", ".pyc", ".pyo"})

def _www_files():
    return sorted(
        p for p in WWW_DIR.rglob("*") if p.is_file() and p.suffix in SERVABLE_SUFFIXES
    )


def _markup_files():
    """Everything a browser can receive markup from: the www routes AND the one shared
    shell they all include, which is where the links actually live now."""
    return _www_files() + [SHARED_SHELL]


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _offsite_script_srcs(text):
    return [src for src in SCRIPT_SRC.findall(text) if OFFSITE_URL.match(src.strip())]


def _vendor_path(url):
    return PUBLIC_DIR / "vendor" / url[len(VENDOR_PREFIX) :]


def _linked_font_stylesheets(text):
    """Vendored stylesheets the markup links whose file on disk declares @font-face.
    leaflet.css is vendored too, so a font sheet is identified by what it declares."""
    return [
        href
        for href in VENDOR_CSS_HREF.findall(text)
        if FONT_FACE_RULE.search(_read(_vendor_path(href)))
    ]


class TestWwwNoExternalCdnAssets(unittest.TestCase):
    def test_scan_finds_the_portal_shells(self):
        # Guards the guard: a broken path would make every assertion below vacuous.
        names = {p.name for p in _www_files()}
        self.assertIn("masar-supervisor.html", names)
        self.assertGreaterEqual(len([n for n in names if n.endswith(".html")]), 5)

    def test_detector_flags_an_offsite_script_and_ignores_a_local_one(self):
        offsite = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
        protocol_relative = "<script src='//cdn.example/x.js'></script>"
        local = '<script type="module" src="/assets/apex/route_supervisor_portal/assets/index.js"></script>'
        self.assertEqual(len(_offsite_script_srcs(offsite)), 1)
        self.assertEqual(len(_offsite_script_srcs(protocol_relative)), 1)
        self.assertEqual(_offsite_script_srcs(local), [])

    def test_no_www_page_loads_a_script_from_another_host(self):
        offenders = []
        for path in _www_files():
            for src in _offsite_script_srcs(_read(path)):
                offenders.append(f"{path.relative_to(APP_ROOT)}: {src}")
        self.assertEqual(
            offenders,
            [],
            "A www page loads executable code from another host. These pages are "
            "authenticated, so the script runs with the user's session and cannot be "
            "reviewed or pinned. Vendor it under apex/public/vendor/ and declare the "
            "package in frontend/package.json:\n  " + "\n  ".join(offenders),
        )

    def test_no_cdn_host_appears_under_www(self):
        offenders = []
        for path in _www_files():
            text = _read(path)
            for host in CDN_HOSTS:
                if host in text:
                    offenders.append(f"{path.relative_to(APP_ROOT)}: {host}")
        self.assertEqual(
            offenders,
            [],
            "CDN host referenced under apex/www/ — serve the asset from apex/public/ "
            "instead. For a font that means a vendored family under "
            "apex/public/vendor/, not a preconnect kept 'just for warming':\n  "
            + "\n  ".join(offenders),
        )

    # `test_no_cdn_host_appears_in_a_portal_bundle_or_its_source` was retired: its twin in
    # apex_core/test_portal_bundle_artifacts.py asks the same question over the same host
    # list but enumerates through `git ls-files`, where this copy globbed `frontend/*/src`
    # and resolved to nothing after the single-portal rewrite.

    # Zombie: `test_masar_supervisor_uses_the_vendored_leaflet_that_exists` stood
    # here. There is no map bundle and no vendored leaflet reference left — the supervisor
    # route is the same 63-byte include as every other, and `"leaflet"` is absent from
    # frontend/package.json. Nothing survives to re-anchor it on.

    def test_detector_flags_a_vendored_stylesheet_href_and_ignores_a_remote_one(self):
        vendored = '<link rel="stylesheet" href="/assets/apex/vendor/cairo-v31/cairo.css" />'
        remote = '<link href="https://fonts.googleapis.com/css2?family=Cairo" rel="stylesheet" />'
        self.assertEqual(
            VENDOR_CSS_HREF.findall(vendored), ["/assets/apex/vendor/cairo-v31/cairo.css"]
        )
        self.assertEqual(VENDOR_CSS_HREF.findall(remote), [])

    def test_every_suffix_under_www_is_classified_as_servable_or_not(self):
        # Fail-closed: an unrecognised suffix means _www_files() silently stopped
        # scanning a file, which would make every assertion above vacuous for it.
        known = SERVABLE_SUFFIXES | NON_SERVABLE_SUFFIXES
        stray = sorted({p.suffix for p in WWW_DIR.rglob("*") if p.is_file()} - known)
        self.assertEqual(
            stray,
            [],
            "unclassified file suffix under apex/www/ — add it to SERVABLE_SUFFIXES "
            f"if a browser can fetch it, to NON_SERVABLE_SUFFIXES if it cannot: {stray}",
        )

    def test_a_python_controller_is_out_of_scope_but_a_template_is_not(self):
        # A CDN host named in a controller's prose is not a request. The same string
        # in a servable file is, so the exemption must be suffix-scoped, not global.
        scanned = {p.suffix for p in _www_files()}
        self.assertIn(".html", scanned)
        self.assertNotIn(".py", scanned)
        self.assertTrue(any(p.suffix == ".py" for p in WWW_DIR.rglob("*") if p.is_file()))

    # Zombie: two detector cases stood here —
    # `test_detector_separates_a_mounting_shell_from_a_redirect_marker` and
    # `test_a_shell_stripped_of_its_font_link_is_still_a_shell_and_reds`. Both classified
    # www/*.html as "a page that MOUNTS an SPA" by looking for `<div id="app">` plus a
    # bundle `<script>`. No www file carries either mark now: each is a 63-byte include
    # and the marks live once, in the shared shell. The narrowing they defended no longer
    # exists, because there is nothing left to narrow — one shell, always a shell.

    def test_the_shared_portal_shell_links_a_vendored_font_stylesheet(self):
        # Every portal route styles itself with a webfont through the one shell it
        # includes. Dropping the CDN link without putting a local one back would leave
        # every page on the device default.
        self.assertTrue(SHARED_SHELL.is_file(), f"{SHARED_SHELL} moved — update this test")
        linked = _linked_font_stylesheets(_read(SHARED_SHELL))
        self.assertTrue(
            linked,
            "the shared portal shell links no vendored font stylesheet — every route "
            "would render in the device default font",
        )
        # Non-vacuity: every www route that RENDERS must reach that shell, or the check
        # above grades a file nobody serves. A meta-refresh redirect page renders no
        # portal and needs no webfont — detected by the refresh itself rather than by an
        # allowlist, so a new redirect is free and a shell that loses its include is not.
        routes = [p for p in _www_files() if p.suffix == ".html"]
        self.assertGreaterEqual(len(routes), 7, f"www route scan found only {routes}")
        detached = [
            str(p.relative_to(APP_ROOT))
            for p in routes
            if "apex_portal_app.html" not in _read(p)
            and 'http-equiv="refresh"' not in _read(p)
        ]
        self.assertEqual(
            detached,
            [],
            "www route(s) that do not include the shared shell, so the font check above "
            f"says nothing about them: {detached}",
        )

    def test_vendored_stylesheets_linked_by_a_shell_resolve_on_disk(self):
        # "No CDN" must not be satisfied by pointing the page at a 404, and a
        # stylesheet that loads is still useless if its own woff2 srcs are missing.
        # This walked _www_files() only, where no vendored href has existed since
        # the shells became includes — the loop body never ran and it passed on an empty
        # population. It walks the shared shell too now, which is where the hrefs are.
        offenders = []
        seen = 0
        for path in _markup_files():
            for href in VENDOR_CSS_HREF.findall(_read(path)):
                seen += 1
                css = _vendor_path(href)
                if not css.is_file():
                    offenders.append(f"{path.relative_to(APP_ROOT)}: {href} is missing")
                    continue
                for src in FONT_FACE_SRC.findall(css.read_text(encoding="utf-8")):
                    if OFFSITE_URL.match(src):
                        offenders.append(f"{css.relative_to(APP_ROOT)}: off-site src {src}")
                    elif not (css.parent / src).is_file():
                        offenders.append(f"{css.relative_to(APP_ROOT)}: {src} is missing")
        self.assertTrue(seen, "no vendored stylesheet href was found — the scan went blind")
        self.assertEqual(offenders, [], "Vendored asset would 404:\n  " + "\n  ".join(offenders))

    def test_vendored_font_families_keep_swap_and_ship_their_licence(self):
        # Google's css2 sets font-display: swap; losing it changes first paint from
        # "show fallback, swap in" to a blocking invisible-text period.
        families = sorted(
            p for p in (PUBLIC_DIR / "vendor").glob("*/*.css") if FONT_FACE_RULE.search(_read(p))
        )
        self.assertGreaterEqual(len(families), 3, "no vendored font family found")
        offenders = []
        for css in families:
            bodies = FONT_FACE_RULE.findall(css.read_text(encoding="utf-8"))
            displays = [FONT_DISPLAY.search(b) for b in bodies]
            values = [m.group(1) for m in displays if m]
            if len(values) != len(bodies) or set(values) != {"swap"}:
                offenders.append(
                    f"{css.relative_to(APP_ROOT)}: {len(bodies)} faces, font-display {values}"
                )
            licence = css.parent / "LICENSE"
            if not licence.is_file():
                offenders.append(f"{css.parent.relative_to(APP_ROOT)}: no LICENSE alongside")
            else:
                # Not every vendored family is SIL OFL -- Thmanyah ships under its own
                # proprietary licence, embedded in the font files themselves rather than
                # a public FAQ. The OFL text is accepted where it applies; where it does
                # not, the LICENSE file must at least name the family it actually covers,
                # so an empty stub or a copy-pasted wrong licence still fails this check.
                text = licence.read_text(encoding="utf-8")
                family = css.parent.name.rsplit("-", 1)[0].replace("-", " ")
                if "SIL OPEN FONT LICENSE" not in text and family.lower() not in text.lower():
                    offenders.append(
                        f"{licence.relative_to(APP_ROOT)}: neither the SIL OFL text nor a "
                        f"licence naming {family!r}"
                    )
        self.assertEqual(offenders, [], "Vendored font problem:\n  " + "\n  ".join(offenders))

    # Zombie: `test_leaflet_stays_pinned_in_the_single_frontend_manifest` stood
    # here, asserting `"leaflet": "1.9.4"` in frontend/package.json. Leaflet is not in
    # that manifest and no map bundle is built — the dependency left with the map
    # surface. Pinning a version nothing depends on is not a contract.


if __name__ == "__main__":
    unittest.main()
