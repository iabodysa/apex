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

Four invariants are pinned here:

  1. No <script src> under apex/www/ points off-site. Third-party executable code
     on a logged-in page is the security case; this is the hard rule.
  2. No known package/script or font CDN host appears anywhere under apex/www/ —
     including in a preconnect, which opens the third-party connection on its own
     even when no stylesheet is ever fetched from it.
  3. /masar-supervisor references the vendored leaflet that actually exists on disk,
     so "no CDN" cannot be satisfied by pointing the page at a 404.
  4. Every vendored font stylesheet a shell links exists on disk, resolves its own
     woff2 files, and keeps font-display: swap — losing swap would change first paint.

Out of scope, tracked separately: the built portal bundles under apex/public/*_portal/
and their sources under frontend/*/src/index.css still @import the same Google Fonts
URL. Removing that needs a frontend rebuild, so this guard covers apex/www/ only and
must not be read as proof that a served page makes no font request.

Run standalone:  python3 -m unittest apex.tests.test_www_no_external_cdn_assets -v
"""

import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
WWW_DIR = APP_ROOT / "www"
PUBLIC_DIR = APP_ROOT / "public"

# Package/script CDNs. A page that needs one of these needs a vendored copy instead.
CDN_HOSTS = (
    "unpkg.com",
    "cdn.jsdelivr.net",
    "jsdelivr.net",
    "cdnjs.cloudflare.com",
    "ajax.googleapis.com",
    "code.jquery.com",
    "stackpath.bootstrapcdn.com",
    "maxcdn.bootstrapcdn.com",
    "esm.sh",
    "cdn.skypack.dev",
    "unpkg.io",
    # Font CDNs. gstatic never appears in markup on its own — it is what the
    # googleapis stylesheet resolves to — but a preconnect to it is exactly how these
    # shells used to warm the third-party connection, so both hosts are listed.
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "fonts.bunny.net",
)

# src on a <script>, whether quoted with ' or ". Protocol-relative //host counts as
# off-site too, which is why the scheme is optional in the URL test below.
SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
OFFSITE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)

LEAFLET_DIR = "leaflet-1.9.4"
LEAFLET_URL_PREFIX = f"/assets/apex/vendor/{LEAFLET_DIR}/"

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


def _www_files():
    return sorted(p for p in WWW_DIR.rglob("*") if p.is_file())


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _offsite_script_srcs(text):
    return [src for src in SCRIPT_SRC.findall(text) if OFFSITE_URL.match(src.strip())]


def _vendor_path(url):
    return PUBLIC_DIR / "vendor" / url[len(VENDOR_PREFIX) :]


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

    def test_masar_supervisor_uses_the_vendored_leaflet_that_exists(self):
        text = _read(WWW_DIR / "masar-supervisor.html")
        self.assertIn(f"{LEAFLET_URL_PREFIX}leaflet.js", text)
        self.assertIn(f"{LEAFLET_URL_PREFIX}leaflet.css", text)
        vendored = PUBLIC_DIR / "vendor" / LEAFLET_DIR
        for asset in ("leaflet.js", "leaflet.css", "images/marker-icon.png"):
            self.assertTrue(
                (vendored / asset).is_file(),
                f"{vendored.relative_to(APP_ROOT)}/{asset} is missing — the page would 404",
            )

    def test_detector_flags_a_vendored_stylesheet_href_and_ignores_a_remote_one(self):
        vendored = '<link rel="stylesheet" href="/assets/apex/vendor/cairo-v31/cairo.css" />'
        remote = '<link href="https://fonts.googleapis.com/css2?family=Cairo" rel="stylesheet" />'
        self.assertEqual(
            VENDOR_CSS_HREF.findall(vendored), ["/assets/apex/vendor/cairo-v31/cairo.css"]
        )
        self.assertEqual(VENDOR_CSS_HREF.findall(remote), [])

    def test_every_portal_shell_links_a_vendored_font_stylesheet(self):
        # Each shell styles itself with a webfont. Dropping the CDN link without
        # putting a local one back would leave the page on the device default.
        shells = [p for p in _www_files() if p.suffix == ".html"]
        self.assertGreaterEqual(len(shells), 7)
        missing = []
        for path in shells:
            # leaflet.css is vendored too, so identify a font sheet by what it
            # declares rather than by where it sits.
            fonts = [
                href
                for href in VENDOR_CSS_HREF.findall(_read(path))
                if FONT_FACE_RULE.search(_read(_vendor_path(href)))
            ]
            if not fonts:
                missing.append(str(path.relative_to(APP_ROOT)))
        self.assertEqual(
            missing,
            [],
            "Portal shell links no vendored font stylesheet — it would render in the "
            "device default font:\n  " + "\n  ".join(missing),
        )

    def test_vendored_stylesheets_linked_by_a_shell_resolve_on_disk(self):
        # "No CDN" must not be satisfied by pointing the page at a 404, and a
        # stylesheet that loads is still useless if its own woff2 srcs are missing.
        offenders = []
        for path in _www_files():
            for href in VENDOR_CSS_HREF.findall(_read(path)):
                css = _vendor_path(href)
                if not css.is_file():
                    offenders.append(f"{path.relative_to(APP_ROOT)}: {href} is missing")
                    continue
                for src in FONT_FACE_SRC.findall(css.read_text(encoding="utf-8")):
                    if OFFSITE_URL.match(src):
                        offenders.append(f"{css.relative_to(APP_ROOT)}: off-site src {src}")
                    elif not (css.parent / src).is_file():
                        offenders.append(f"{css.relative_to(APP_ROOT)}: {src} is missing")
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
            elif "SIL OPEN FONT LICENSE" not in licence.read_text(encoding="utf-8"):
                offenders.append(f"{licence.relative_to(APP_ROOT)}: not the SIL OFL text")
        self.assertEqual(offenders, [], "Vendored font problem:\n  " + "\n  ".join(offenders))

    def test_leaflet_stays_pinned_in_the_single_frontend_manifest(self):
        # The vendored copy is only trustworthy while the manifest names the exact
        # version it was taken from; a caret would let the two drift apart.
        manifest = APP_ROOT.parent / "frontend" / "package.json"
        self.assertIn('"leaflet": "1.9.4"', _read(manifest))


if __name__ == "__main__":
    unittest.main()
