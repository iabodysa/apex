"""E2E breadcrumb spec — the module breadcrumb points at the module ROOT (P-108).

WHY: P-108 rewrites each module root Workspace's ``creation`` so the Desk
breadcrumb for a DocType in that module resolves to the module root
(``module_wise_workspaces[module][0]``, breadcrumbs.js:161 → href
``/app/<slug(workspace)>``, breadcrumbs.js:117). This spec is the RUNTIME half of
the P-108 verification: it opens a Habitat DocType list and a Salis DocType list
in a real authenticated Desk session and asserts the module breadcrumb anchor
links to ``/app/habitat`` and ``/app/salis`` respectively — not to a sub-workspace
(e.g. ``/app/fleet`` or ``/app/custody``).

HARNESS: reuses the committed Playwright Desk-auth helper ``e2e/desk_auth.py``
(``authenticated_page``), which reads the synthetic screenshot-bot credential from
the gitignored ``e2e/.env.local`` (template: ``e2e/.env.local.example``). The
screenshot user's default roles (Fleet Manager/Supervisor, Accommodation Manager,
Resident Supervisor — see e2e/setup_screenshot_user.py) make BOTH the Habitat and
Salis modules visible, which the breadcrumb requires (breadcrumbs.js:111).

RUN (from bench root, against a running site — same pattern as desk_auth.py):
    cp e2e/.env.local.example e2e/.env.local        # then set SCREENSHOT_PW
    set -a; . <apex>/e2e/.env.local; set +a
    # one-time: provision the screenshot user (see e2e/setup_screenshot_user.py)
    <bench>/env/bin/python <apex>/e2e/breadcrumb_root_spec.py
    # exit 0 = both module breadcrumbs resolve to their module root; non-zero = fail

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
    ("accommodation-building", "/app/habitat"),  # Habitat module DocType list
    ("salis-vehicle", "/app/salis"),             # Salis module DocType list
]


def _breadcrumb_hrefs(page, base, list_route):
    """Open a DocType list and return the raw hrefs of its navbar breadcrumb anchors."""
    page.goto(f"{base}/app/{list_route}", wait_until="networkidle")
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
            hrefs = _breadcrumb_hrefs(page, base, list_route)
            ok = expected_root in (hrefs or [])
            print(f"{'PASS' if ok else 'FAIL'} /app/{list_route}: breadcrumbs={hrefs} expected={expected_root}")
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
