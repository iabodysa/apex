# Copyright (c) 2026, AFMCO and contributors
"""No portal page under apex/www/ may pull an executable asset from a CDN.

/masar-supervisor used to load leaflet@1.9.4 from unpkg.com. That put a runtime
dependency of an AUTHENTICATED page outside the npm manifest, outside the single
frontend/package-lock.json, and outside the dompurify/ws security overrides — an
unpinned third-party script that executes with the supervisor's session, plus a
hard failure on an offline or egress-filtered bench. Leaflet is now vendored at
apex/public/vendor/leaflet-<version>/ and pinned in frontend/package.json.

Three invariants are pinned here:

  1. No <script src> under apex/www/ points off-site. Third-party executable code
     on a logged-in page is the security case; this is the hard rule.
  2. No known package/script CDN host appears anywhere under apex/www/.
  3. /masar-supervisor references the vendored leaflet that actually exists on disk,
     so "no CDN" cannot be satisfied by pointing the page at a 404.

Known exception, deliberately NOT in CDN_HOSTS: the Google Fonts stylesheet
(fonts.googleapis.com / fonts.gstatic.com) that every www shell links. It ships no
executable code and every page declares a local font fallback, so it degrades
cosmetically rather than failing. Removing it is a repo-wide change across all
portal shells, tracked separately — this guard must not silently bless it, so it
is named here instead of being folded into the host list.

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
)

# src on a <script>, whether quoted with ' or ". Protocol-relative //host counts as
# off-site too, which is why the scheme is optional in the URL test below.
SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
OFFSITE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)

LEAFLET_DIR = "leaflet-1.9.4"
LEAFLET_URL_PREFIX = f"/assets/apex/vendor/{LEAFLET_DIR}/"


def _www_files():
    return sorted(p for p in WWW_DIR.rglob("*") if p.is_file())


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _offsite_script_srcs(text):
    return [src for src in SCRIPT_SRC.findall(text) if OFFSITE_URL.match(src.strip())]


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
            "instead:\n  " + "\n  ".join(offenders),
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

    def test_leaflet_stays_pinned_in_the_single_frontend_manifest(self):
        # The vendored copy is only trustworthy while the manifest names the exact
        # version it was taken from; a caret would let the two drift apart.
        manifest = APP_ROOT.parent / "frontend" / "package.json"
        self.assertIn('"leaflet": "1.9.4"', _read(manifest))


if __name__ == "__main__":
    unittest.main()
