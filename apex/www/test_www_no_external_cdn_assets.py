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

Two scoping rules keep those invariants aimed at what a browser actually receives:

  * Only SERVABLE suffixes are scanned. A ``.py`` under apex/www/ is a server-side
    controller — Frappe's own ``can_render`` refuses to serve it — so a CDN hostname
    written in its prose (e.g. the recorded acceptance of the map tile source in
    www/masar_supervisor.py) reaches no client and is not a third-party request.
  * "Portal shell", the population held to the vendored-font rule, is decided
    STRUCTURALLY: a shell is a page that MOUNTS an SPA — it has the ``#app`` node
    and the module script that loads a portal bundle. A redirect-only marker such as
    www/housing-count.html has neither and never paints, so requiring a font
    stylesheet of it would be a false positive. This is deliberately not a filename
    allowlist: a new shell is covered the moment it mounts, with no list to update.

The SPA a shell mounts is covered too. The sources under frontend/*/src/ and the built
bundles under apex/public/*_portal/ once @imported the same Google Fonts URL, so a
served page still made a third-party font request even with apex/www/ itself clean.
Those imports are gone, and invariant 5 pins it — a shell being clean is not evidence
about the bundle the browser actually executes.

Run standalone:  python3 -m unittest apex.www.test_www_no_external_cdn_assets -v
"""

import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
WWW_DIR = APP_ROOT / "www"
PUBLIC_DIR = APP_ROOT / "public"
REPO_ROOT = APP_ROOT.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

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

# Suffixes a browser can receive from apex/www. Anything not listed here must be
# classified below, so a new asset type cannot escape the scan by omission.
SERVABLE_SUFFIXES = frozenset({".html", ".md", ".js", ".css", ".json", ".svg", ".txt"})
# Server-side only: TemplatePage.can_render refuses a Python suffix outright
# (template_page.py:70-75), so these bytes never leave the server. .pyc/.pyo are
# the __pycache__ artefacts a local test run leaves behind.
NON_SERVABLE_SUFFIXES = frozenset({".py", ".pyc", ".pyo"})

# Text a bundler can carry a URL in, on either side of the build.
BUNDLE_SUFFIXES = frozenset({".css", ".js", ".ts", ".vue", ".html", ".json"})

# The two marks of a page that MOUNTS an SPA. A shell has both; a redirect marker,
# an error stub or a plain server-rendered page has neither.
MOUNT_NODE = re.compile(r"<div\b[^>]*\bid\s*=\s*[\"']app[\"']", re.IGNORECASE)
BUNDLE_SCRIPT = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*[\"']/assets/apex/[A-Za-z0-9_]+/assets/index\.js[\"']",
    re.IGNORECASE,
)


def _www_files():
    return sorted(
        p for p in WWW_DIR.rglob("*") if p.is_file() and p.suffix in SERVABLE_SUFFIXES
    )


def _portal_bundle_files():
    """Portal SPA sources plus the built bundles a shell mounts. Scanning src/ rather
    than each frontend app root is what keeps node_modules out of the walk."""
    roots = sorted(FRONTEND_DIR.glob("*/src")) + sorted(PUBLIC_DIR.glob("*_portal/assets"))
    return sorted(
        p
        for root in roots
        for p in root.rglob("*")
        if p.is_file() and p.suffix in BUNDLE_SUFFIXES
    )


def _is_portal_shell(text):
    """True when the markup mounts a portal SPA — the font rule applies only here."""
    return bool(MOUNT_NODE.search(text) and BUNDLE_SCRIPT.search(text))


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

    def test_no_cdn_host_appears_in_a_portal_bundle_or_its_source(self):
        # A clean shell is not evidence about the SPA it mounts: the bundle is what the
        # browser executes, so an @import there is still a third-party request.
        files = _portal_bundle_files()
        sides = {"frontend" if FRONTEND_DIR in p.parents else "public" for p in files}
        self.assertEqual(
            sides,
            {"frontend", "public"},
            f"one side of the scan matched nothing ({len(files)} files) — the glob broke",
        )
        offenders = []
        for path in files:
            text = _read(path)
            for host in CDN_HOSTS:
                if host in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {host}")
        self.assertEqual(
            offenders,
            [],
            "CDN host in a portal SPA source or its built bundle — the shell being "
            "clean does not help, the browser still makes the request. Vendor it under "
            "apex/public/vendor/ and rebuild the bundle:\n  " + "\n  ".join(offenders),
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

    def test_detector_separates_a_mounting_shell_from_a_redirect_marker(self):
        shell = _read(WWW_DIR / "masar-supervisor.html")
        marker = '<!doctype html><html><body><p>Moved to <a href="/housing">/housing</a></p></body></html>'
        self.assertTrue(_is_portal_shell(shell))
        self.assertFalse(_is_portal_shell(marker))
        self.assertFalse(_is_portal_shell('<div id="app"></div>'), "mount alone is not a shell")

    def test_a_shell_stripped_of_its_font_link_is_still_a_shell_and_reds(self):
        # The other direction of the narrowing: excluding redirect markers must not
        # buy a real shell an exemption. Strip the font link and it must still fail.
        text = _read(WWW_DIR / "masar-supervisor.html")
        self.assertTrue(_linked_font_stylesheets(text), "fixture shell has no font link to strip")
        stripped = re.sub(r'<link[^>]*vendor/cairo-[^>]*>', "", text)
        self.assertTrue(_is_portal_shell(stripped), "stripping a font link must not un-classify it")
        self.assertEqual(_linked_font_stylesheets(stripped), [])

    def test_every_portal_shell_links_a_vendored_font_stylesheet(self):
        # Each shell styles itself with a webfont. Dropping the CDN link without
        # putting a local one back would leave the page on the device default.
        shells = [p for p in _www_files() if p.suffix == ".html" and _is_portal_shell(_read(p))]
        self.assertGreaterEqual(len(shells), 7, f"shell scan found only {shells}")
        missing = [
            str(path.relative_to(APP_ROOT))
            for path in shells
            if not _linked_font_stylesheets(_read(path))
        ]
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
