"""E2E breadcrumb spec — the module breadcrumb points at the module ROOT.

WHY: the Desk breadcrumb for a DocType resolves to whichever Workspace of that
module sorts FIRST by ``creation`` (``module_wise_workspaces[module][0]``,
breadcrumbs.js:161 → href ``/app/<slug(workspace)>``, breadcrumbs.js:117), so a
module root Workspace stamped after one of its sub-workspaces silently hands the
breadcrumb to that sub-workspace. The app keeps each module root sorting first
(apex/patches/v1_x/reorder_root_workspace_creation.py); this spec is the RUNTIME
half of that guarantee: it opens a Habitat DocType list and a Salis DocType list
in a real authenticated Desk session and asserts the module breadcrumb anchor
links to ``/app/habitat`` and ``/app/salis`` respectively — not to a sub-workspace
(e.g. ``/app/fleet`` or ``/app/custody``).

HARNESS: reuses the committed Playwright Desk-auth helper ``e2e/desk_auth.py``
(``authenticated_page``), which reads the synthetic screenshot-bot credential from
the gitignored ``e2e/.env.local`` (template: ``e2e/.env.local.example``). The
screenshot user's declared roles (Fleet Manager/Supervisor, Accommodation Manager,
Resident Supervisor — see e2e/setup_screenshot_user.py) make BOTH the Habitat and
Salis modules visible, which the breadcrumb requires (breadcrumbs.js:111).

WHO RUNS IT, AND HOW — this spec does NOT run in CI. The only e2e file any
workflow invokes is ``portal_smoke_spec.py`` (.github/workflows/portal-tests.yml,
job ``portal-smoke``); nothing else under ``e2e/`` is wired to a workflow. This
one needs an authenticated Desk session under the provisioned screenshot-bot
account plus its gitignored credential, so it is run BY THE MAINTAINER on a local
bench, against a served site — and it must be re-run whenever a Workspace in
Habitat or Salis is added, renamed, or re-stamped, and whenever the root-ordering
patch changes. (The ``portal-smoke`` job already provisions a bench and installs
Playwright, so this spec COULD be added there as a second step; that is a separate
change to a workflow file this spec does not own, and it must not be wired in
while the spec is knowingly red — see STATUS.)

RUN (from bench root, against a running site — same pattern as desk_auth.py):
    cp e2e/.env.local.example e2e/.env.local        # then set SCREENSHOT_PW
    set -a; . <apex>/e2e/.env.local; set +a
    # one-time: provision the screenshot user (see e2e/setup_screenshot_user.py)
    <bench>/env/bin/python <apex>/e2e/breadcrumb_root_spec.py
    # exit 0 = both module breadcrumbs resolve to their module root; non-zero = fail

STATUS: expected RED on ``/app/building``, which reports
``["/app/backend-engines", "/app/building"]`` because the Habitat root Workspace
sorts after Backend Engines by ``creation``. That is a real product defect tracked
separately; it is NOT to be skipped, xfailed or baselined away here — a green from
a weakened assertion would be worth less than this red.

This is a self-contained assertion script (not a pytest/unittest case) because the
existing e2e harness is a bench-venv Playwright runner, not a JS Playwright project.
"""
import sys
from pathlib import Path

# Make the sibling helper importable whether run as a file or a module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from desk_auth import authenticated_page  # noqa: E402

# (DocType-list route under /app, expected module-root breadcrumb href)
_CASES = [
    ("building", "/app/habitat"),      # Habitat module DocType list
    ("salis-vehicle", "/app/salis"),   # Salis module DocType list
]

# The Desk router settles a route within a second of boot; longer means a dead page.
_ROUTE_TIMEOUT_MS = 10000
# Standard routes a /app/<slug> resolves to when the slug IS a readable DocType
# (router.js set_doctype_route); anything else means the slug matched no DocType.
_DOCTYPE_VIEWS = ("List", "Form", "Tree", "Report")


class RouteNotResolved(AssertionError):
    """A ``/app/<slug>`` route did not resolve to a DocType view."""


def _assert_route_resolved(list_route, desk_route):
    """Return the DocType ``/app/<list_route>`` resolved to; raise if it resolved to none.

    WHY this runs BEFORE the breadcrumb wait: Frappe registers a /app route only for
    a DocType the session can READ (router.js:125-127). A renamed DocType — or one
    the screenshot user lost read on — therefore leaves the route unresolved, renders
    the not-found page and an EMPTY #navbar-breadcrumbs, so waiting for a breadcrumb
    anchor would die as a silent selector timeout that names nothing.
    """
    if len(desk_route) > 1 and desk_route[0] in _DOCTYPE_VIEWS:
        return desk_route[1]
    raise RouteNotResolved(
        f"/app/{list_route} did not resolve to a DocType view: the Desk router settled "
        f"on {desk_route}. Either no DocType slugs to '{list_route}' (renamed?), or the "
        f"screenshot user cannot read it. Fix the route in _CASES, or the role grant in "
        f"e2e/setup_screenshot_user.py — do not read the empty breadcrumb as a result."
    )


def _resolved_route(page, base, list_route):
    """Open a DocType list and return the route array the Desk router settled on."""
    # Imported here, not at module scope, so the pure assertion above stays importable
    # (and provable) on a plain python with no playwright installed.
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    page.goto(f"{base}/app/{list_route}", wait_until="networkidle")
    try:
        page.wait_for_function(
            "() => window.frappe && frappe.router && (frappe.router.current_route || []).length",
            timeout=_ROUTE_TIMEOUT_MS,
        )
    except PlaywrightTimeout as exc:
        raise RouteNotResolved(
            f"/app/{list_route}: the Desk router never settled within "
            f"{_ROUTE_TIMEOUT_MS}ms — the Desk did not boot at all."
        ) from exc
    return page.evaluate("() => frappe.get_route()")


def _breadcrumb_hrefs(page):
    """Return the raw hrefs of the navbar breadcrumb anchors on the current page."""
    # Breadcrumbs render after the list view boots; wait for at least one anchor.
    page.wait_for_selector("#navbar-breadcrumbs a", timeout=15000)
    page.wait_for_timeout(1000)
    return page.eval_on_selector_all(
        "#navbar-breadcrumbs a", "els => els.map(e => e.getAttribute('href'))"
    )


def run():
    failures = []
    with authenticated_page() as (page, base):
        for list_route, expected_root in _CASES:
            doctype = _assert_route_resolved(list_route, _resolved_route(page, base, list_route))
            hrefs = _breadcrumb_hrefs(page)
            ok = expected_root in (hrefs or [])
            print(
                f"{'PASS' if ok else 'FAIL'} /app/{list_route} -> {doctype}: "
                f"breadcrumbs={hrefs} expected={expected_root}"
            )
            if not ok:
                failures.append((list_route, expected_root, hrefs))
    if failures:
        for list_route, expected_root, hrefs in failures:
            print(f"  MISMATCH {list_route}: {expected_root} not in {hrefs}")
        return 1
    print("OK: every module breadcrumb resolves to its module root")
    return 0


if __name__ == "__main__":
    sys.exit(run())
