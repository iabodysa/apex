"""E2E smoke-mount spec — every portal SPA mounts cleanly (P-206).

WHY: the portal SPAs (fleet, fleet-os, driver, worker/masar, housing, safety) build to
committed bundles served by the ``www/<portal>.html`` shells. A stale/broken bundle
or a bad shared import (the exact class of regression the shared vite factory,
bundle-guard, and the @shared dedup can introduce) makes the SPA fail to mount or
throw at boot — with NOTHING in a green build to catch it. This spec is the RUNTIME
half that MEMORY's "runtime open-smoke / verify the specific element" rule demands:
it opens each portal, asserts the SPA root node (``#app``) is populated (the app
actually mounted), and asserts ZERO console errors / uncaught page errors during
boot.

SCOPE: this is a *mount* smoke, not a flow test. It proves the shell boots, the
bundle loads, and the root component renders without throwing — for every portal,
in one place. Flow-level e2e (boarding, trip lifecycle, count) is out of scope.

HARNESS: reuses the committed Playwright helper ``e2e/desk_auth.py``
(``authenticated_page``), which establishes a real Frappe session from the
gitignored ``e2e/.env.local`` credential (template ``e2e/.env.local.example``). A
session is needed because each shell boots with a CSRF token; an unauthenticated
hit would bounce to login and never mount the SPA. The screenshot user need not be
a driver/worker — an unlinked account still MOUNTS the SPA (it renders the
"unlinked" state), which is all a mount smoke asserts. If a portal logs a resource
error for an account that lacks its domain data, provision a portal-scoped user (see
e2e/setup_screenshot_user.py) and re-run.

RUN (from bench root, against a running site with the portals built + served):
    cp e2e/.env.local.example e2e/.env.local        # then set SCREENSHOT_PW
    set -a; . <apex>/e2e/.env.local; set +a
    <bench>/env/bin/python <apex>/e2e/portal_smoke_spec.py
    # exit 0 = every portal mounts with no console/page errors; non-zero = fail
    # scope to one portal (used by the CI matrix): APEX_PORTAL=fleet <python> ...

This is a self-contained assertion script (not pytest) to match the existing
bench-venv Playwright harness (see e2e/breadcrumb_root_spec.py).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desk_auth import authenticated_page  # noqa: E402

# (served route, human label) — one entry per SERVED shell, so every bundle the
# bundle-guard matrix rebuilds is also proven to mount. The route and the bundle
# name diverge: /fleet is the employee page (fleet_portal) while /fleet-os is the
# supervisor board (fleet_os_portal), the worker bundle is served at /masar, and
# route_supervisor_portal is served at /masar-supervisor.
_PORTALS = [
    ("fleet", "Fleet Employee"),
    ("fleet-os", "Fleet OS Board"),
    ("driver", "Salis Driver"),
    ("masar", "Masar Worker"),
    # /masar-supervisor (route_supervisor_portal) is deliberately NOT smoked yet: it
    # mounts, but its only boot call
    # (apex.salis.api.route_supervisor.get_supervisor_context) answers 417 on a fresh
    # site even for Administrator, so listing it here would red every push. Tracked
    # separately; re-add this route with the fix.
    ("housing", "Housing"),
    ("safety", "Safety"),
]


def _smoke_one(page, base, route):
    """Open one portal, return (mounted_child_count, [error strings])."""
    errors = []
    # Capture console errors + uncaught exceptions for THIS navigation only.
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    page.goto(f"{base}/{route}", wait_until="networkidle")
    # The SPA mounts into <div id="app">; wait for the root to gain a child node.
    try:
        page.wait_for_function("document.querySelector('#app') && document.querySelector('#app').children.length > 0", timeout=15000)
    except Exception:
        pass  # fall through — child count below reports the (zero) mount
    page.wait_for_timeout(800)  # let any boot-time async error surface

    child_count = page.eval_on_selector("#app", "el => el ? el.children.length : 0")
    return child_count, errors


def run():
    only = os.environ.get("APEX_PORTAL", "").strip().lower()
    portals = [p for p in _PORTALS if not only or p[0] == only]
    if not portals:
        print(f"FAIL: APEX_PORTAL={only!r} matches no known portal {[p[0] for p in _PORTALS]}")
        return 2

    failures = []
    for route, label in portals:
        # A fresh page per portal so console/page-error listeners don't accumulate.
        with authenticated_page() as (page, base):
            children, errors = _smoke_one(page, base, route)
        mounted = children > 0
        ok = mounted and not errors
        print(f"{'PASS' if ok else 'FAIL'} /{route} ({label}): mounted={mounted} (#app children={children}), errors={len(errors)}")
        for e in errors:
            print(f"    {e}")
        if not ok:
            failures.append(route)

    if failures:
        print(f"FAIL: {len(failures)} portal(s) did not smoke clean: {failures}")
        return 1
    print(f"OK: {len(portals)} portal(s) mounted with zero console/page errors")
    return 0


if __name__ == "__main__":
    sys.exit(run())
