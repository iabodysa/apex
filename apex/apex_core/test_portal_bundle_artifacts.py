# Copyright (c) 2026, AFMCO and contributors
"""Guard: what the portal build EMITS into apex/public/ must be safe to serve publicly.

apex/public/ is not behind the application. `frappe/app.py:527` wraps the WSGI app in
werkzeug's ``SharedDataMiddleware({"/assets": <sites>/assets})``, and sites/assets/apex
is a symlink to this package's public/ directory. That middleware answers before any
Frappe request handling, so it runs with no session, no login check and no role check:
every byte under apex/public/ is readable by an anonymous visitor. Two things had been
emitted there that should never have been public.

  1. Every built ``<portal>/index.html`` shipped frappe-ui's boot template as LITERAL
     text -- ``{% for key in boot %}`` and friends, unrendered, because that plugin
     assumes Frappe renders the built index.html and here it is a static file. It also
     published a second, ungated SPA mount point next to the real one. The real mount
     point is the www route (www/<portal>.html), which checks the visitor's roles and
     injects csrf_token; the built index.html is a Vite artifact nobody should reach,
     so the build now replaces it with an inert stub.
  2. The route-supervisor entry loaded leaflet from unpkg.com and five portal
     stylesheets @imported Google Fonts, so the bundles reached third-party hosts from
     authenticated pages. Both families are vendored under apex/public/vendor/ and
     declared by the hosting shell instead.

Companion to apex/www/test_www_no_external_cdn_assets.py, which pins the same
no-CDN invariant for apex/www/ and explicitly leaves the built bundles to this guard.

The Jinja scan is delimiter-specific on purpose. ``{{``, ``}}``, ``{#`` and ``%}`` all
occur naturally in minified JS and CSS (``100%}``, a private class field, a template
literal), so those are asserted on .html artifacts only — but on EVERY .html under
apex/public/, not just the portal bundles, because the middleware publishes the whole
directory. ``{%`` does not occur in minified output, so it is asserted across every
text file the vite factory writes.

Home: the tree this guards is apex/public/, which frappe's test runner prunes
(frappe/test_runner.py), so no test can sit inside it; apex/tests/ is shrink-only under
the colocation ratchet; and apex/www/ is off-limits because the companion guard above
greps every file there for CDN host strings, which this module has to spell out. The
bundles are shared across Salis and Habitat portals, so the kernel package owns it.

Run standalone:  python3 -m unittest apex.apex_core.test_portal_bundle_artifacts -v
"""

import re
import subprocess
import unittest
from pathlib import Path

import apex
from apex.tests.source_tree import CDN_HOSTS

APP_ROOT = Path(apex.__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent
PUBLIC_DIR = APP_ROOT / "public"
FRONTEND_DIR = REPO_ROOT / "frontend"

# Built SPA output dirs, i.e. everything the vite factory writes with emptyOutDir.
PORTAL_DIRS = sorted(p for p in PUBLIC_DIR.glob("*_portal") if p.is_dir())

JINJA_HTML_DELIMS = ("{{", "}}", "{%", "%}", "{#", "#}")
JINJA_STATEMENT_OPEN = "{%"

SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
LINK_HREF = re.compile(r"<link\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
OFFSITE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.IGNORECASE)
APP_MOUNT = re.compile(r"<div\b[^>]*\bid\s*=\s*[\"']app[\"']", re.IGNORECASE)

LEAFLET_PREFIX = "/assets/apex/vendor/leaflet-1.9.4/"
# The six portal SPAs build from one consolidated frontend/apex_portal/ tree into one
# apex/public/apex_portal/ output (frontend/apex_portal/vite.config.js:13,52); there is
# no per-portal dev entry any more, so this names the module that actually loads
# Leaflet -- LEAFLET_STYLE / LEAFLET_SCRIPT in leafletAdapter.js, injected as a <link>
# and a <script> at runtime instead of a static tag in an index.html.
SUPERVISOR_ENTRY = (
    FRONTEND_DIR / "apex_portal" / "features" / "transport-supervisor" / "leafletAdapter.js"
)


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _built_files():
    return sorted(p for d in PORTAL_DIRS for p in d.rglob("*") if p.is_file())


def _shipped_html():
    """Every .html under apex/public/, not just the portal bundles.

    The Jinja scan keys off what is SERVED, not off who wrote it: SharedDataMiddleware
    publishes the whole of apex/public/, so an index.html dropped into any other
    directory there leaks exactly the same way a portal one does. Scoping this to
    `*_portal` left that reachable and unasserted.
    """
    return sorted(p for p in PUBLIC_DIR.rglob("*.html") if p.is_file())


def _built_index_pages():
    return sorted(d / "index.html" for d in PORTAL_DIRS if (d / "index.html").is_file())


def _tracked_frontend_files():
    """Tracked files under frontend/, so node_modules can never widen the scan."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", "frontend"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return sorted(REPO_ROOT / n for n in names if n)


def _offsite(urls):
    return [u for u in urls if OFFSITE_URL.match(u.strip())]


class TestPortalBundleArtifacts(unittest.TestCase):
    def test_scan_finds_every_portal_bundle(self):
        # Guards the guard: a wrong path would make every assertion below vacuous.
        # One consolidated build now emits every portal persona from one Vite root
        # (frontend/apex_portal/vite.config.js) into one apex/public/apex_portal/
        # output, in place of the six separately-built portal directories.
        names = {d.name for d in PORTAL_DIRS}
        self.assertEqual(names, {"apex_portal"})
        self.assertGreater(len(_built_files()), 50, "built tree scan returned implausibly little")
        self.assertEqual(len(_built_index_pages()), len(PORTAL_DIRS))
        # The Jinja scan runs over the whole served tree, so it must at least reach
        # every portal index page — a bad PUBLIC_DIR would make it silently vacuous.
        self.assertTrue(set(_built_index_pages()).issubset(set(_shipped_html())))

    def test_no_built_html_artifact_contains_jinja_delimiters(self):
        offenders = []
        for path in _shipped_html():
            text = _read(path) or ""
            for delim in JINJA_HTML_DELIMS:
                if delim in text:
                    offenders.append(f"{path.relative_to(APP_ROOT)}: {delim}")
        self.assertEqual(
            offenders,
            [],
            "A built artifact ships raw Jinja. apex/public/ is served as static files "
            "by SharedDataMiddleware (frappe/app.py:527), so nothing there is ever "
            "rendered — the template leaks to anonymous visitors as literal text. Boot "
            "data belongs in the www route that mounts the SPA:\n  " + "\n  ".join(offenders),
        )

    def test_no_built_artifact_of_any_type_opens_a_jinja_statement(self):
        offenders = []
        for path in _built_files():
            text = _read(path)
            if text and JINJA_STATEMENT_OPEN in text:
                offenders.append(str(path.relative_to(APP_ROOT)))
        self.assertEqual(
            offenders,
            [],
            "A built artifact contains a Jinja statement delimiter outside HTML:\n  "
            + "\n  ".join(offenders),
        )

    def test_built_index_pages_are_inert_and_are_not_a_second_mount_point(self):
        offenders = []
        for path in _built_index_pages():
            text = _read(path) or ""
            rel = path.relative_to(APP_ROOT)
            if APP_MOUNT.search(text):
                offenders.append(f"{rel}: has the SPA mount element")
            if SCRIPT_SRC.findall(text):
                offenders.append(f"{rel}: loads a script")
        self.assertEqual(
            offenders,
            [],
            "A built index.html still boots the SPA. That is a public, role-free mount "
            "point beside the permission-checked www route; the build must emit an "
            "inert stub there instead:\n  " + "\n  ".join(offenders),
        )

    def test_no_built_artifact_references_a_cdn_host(self):
        offenders = []
        for path in _built_files():
            text = _read(path)
            if text is None:
                continue
            for host in CDN_HOSTS:
                if host in text:
                    offenders.append(f"{path.relative_to(APP_ROOT)}: {host}")
        self.assertEqual(
            offenders,
            [],
            "A built bundle reaches a third-party host. These bundles run on "
            "authenticated pages, so the request leaks a hit per page load and the code "
            "is unpinned. Vendor it under apex/public/vendor/:\n  " + "\n  ".join(offenders),
        )

    def test_no_built_html_loads_a_script_or_stylesheet_off_site(self):
        # Host-name matching only catches hosts already known; this catches any host.
        offenders = []
        for path in _built_files():
            if path.suffix.lower() != ".html":
                continue
            text = _read(path) or ""
            for url in _offsite(SCRIPT_SRC.findall(text) + LINK_HREF.findall(text)):
                offenders.append(f"{path.relative_to(APP_ROOT)}: {url}")
        self.assertEqual(
            offenders, [], "Built page loads an off-site asset:\n  " + "\n  ".join(offenders)
        )

    def test_no_tracked_frontend_source_references_a_cdn_host(self):
        # The build input is the real fix: a vendored bundle regresses the moment a
        # source file reintroduces the URL, and the next rebuild ships it again.
        files = _tracked_frontend_files()
        self.assertIsNotNone(files, "git could not list frontend/ — scan would be vacuous")
        self.assertGreater(len(files), 50, "frontend scan returned implausibly few files")
        offenders = []
        for path in files:
            text = _read(path)
            if text is None:
                continue
            for host in CDN_HOSTS:
                if host in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {host}")
        self.assertEqual(
            offenders,
            [],
            "A portal source references a third-party host — the next build ships it:\n  "
            + "\n  ".join(offenders),
        )

    def test_supervisor_entry_points_at_a_vendored_leaflet_that_exists(self):
        # "No CDN" must not be satisfiable by pointing the dev entry at a 404.
        text = _read(SUPERVISOR_ENTRY)
        self.assertIsNotNone(text, f"{SUPERVISOR_ENTRY} is missing")
        self.assertIn(f"{LEAFLET_PREFIX}leaflet.js", text)
        self.assertIn(f"{LEAFLET_PREFIX}leaflet.css", text)
        vendored = PUBLIC_DIR / "vendor" / "leaflet-1.9.4"
        for asset in ("leaflet.js", "leaflet.css"):
            self.assertTrue((vendored / asset).is_file(), f"{vendored}/{asset} is missing")

    def test_detectors_flag_synthetic_offenders_and_pass_clean_markup(self):
        stub = '<link rel="stylesheet" href="/assets/apex/vendor/cairo-v31/cairo.css" />'
        remote_css = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo" />'
        remote_js = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'
        protocol_relative = "<script src='//cdn.example/x.js'></script>"
        local_js = '<script type="module" src="/assets/apex/worker_portal/assets/index.js"></script>'
        self.assertEqual(_offsite(LINK_HREF.findall(stub)), [])
        self.assertEqual(len(_offsite(LINK_HREF.findall(remote_css))), 1)
        self.assertEqual(len(_offsite(SCRIPT_SRC.findall(remote_js))), 1)
        self.assertEqual(len(_offsite(SCRIPT_SRC.findall(protocol_relative))), 1)
        self.assertEqual(_offsite(SCRIPT_SRC.findall(local_js)), [])
        self.assertTrue(APP_MOUNT.search('<div id="app"></div>'))
        self.assertFalse(APP_MOUNT.search("<div id='application'></div>"))
        self.assertTrue(any(d in "{% for key in boot %}" for d in JINJA_HTML_DELIMS))


if __name__ == "__main__":
    unittest.main()
