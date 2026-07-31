"""Playwright Desk-auth helper — log a screenshot session into the Frappe Desk.

WHY: screenshotting a Desk page needs an authenticated, NON-Guest session — an
unauthenticated hit bounces to login and never renders the page. This helper
reads a synthetic screenshot-bot credential from the environment (never inline)
and establishes the Frappe session cookie, so a task can then goto /app/<page>
and screenshot it.

CRED LOCATION (gitignored): e2e/.env.local  — keys BASE_URL, SCREENSHOT_USER,
SCREENSHOT_PW, and the optional SITE_NAME. A committed template lives at
e2e/.env.local.example. The matching Desk user is provisioned idempotently by
e2e/setup_screenshot_user.py.

SITE_NAME picks WHICH site on a multi-site bench answers, and one bench serving
several sites is the normal case here. `bench serve` started without `--site`
resolves the site from the request host, and every browser on this machine sends
the same `localhost` — so without this the site is whatever that hostname happens
to map to, which is not a fact a capture may leave to chance when one of the
sites is somebody else's. When set, it is sent as `X-Frappe-Site-Name`, which
frappe/app.py prefers over the host. Assert `frappe.boot.sitename` in the browser
before writing an artifact rather than trusting the header round-tripped.

ONE-TIME SETUP (bench root) — run the setup file as ONE compiled unit; do NOT
pipe it line-by-line (bench console feeds stdin cell-by-cell and breaks if/else):
    cp e2e/.env.local.example e2e/.env.local   # then edit SCREENSHOT_PW + SITE_NAME
    set -a; . <apex>/e2e/.env.local; set +a
    p='<apex>/e2e/setup_screenshot_user.py'
    echo "exec(compile(open('$p').read(),'$p','exec'),{'__name__':'setup'})" | bench --site "$SITE_NAME" console

USE FROM A SCREENSHOT TASK:
    from e2e.desk_auth import authenticated_page
    with authenticated_page() as (page, base):
        page.goto(f"{base}/app/operations-control", wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path="e2e/screenshots/operations-control.png", full_page=True)

SMOKE (proves auth + captures the canonical non-portal page) — use the bench
venv python, which has playwright + the chromium browser installed:
    set -a; . <apex>/e2e/.env.local; set +a
    <bench>/env/bin/python <apex>/e2e/desk_auth.py   # -> e2e/screenshots/operations-control.png
"""
import os
import sys
from contextlib import contextmanager
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent / ".env.local"


def _load_env():
    """Load e2e/.env.local into os.environ (does not overwrite already-set vars).

    Kept dependency-free (no python-dotenv) so the helper runs on a bare bench.
    """
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def _creds():
    _load_env()
    base = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    user = os.environ.get("SCREENSHOT_USER")
    pw = os.environ.get("SCREENSHOT_PW")
    site = os.environ.get("SITE_NAME") or ""
    if not user or not pw:
        raise SystemExit(
            "SCREENSHOT_USER / SCREENSHOT_PW not set — create e2e/.env.local "
            "from e2e/.env.local.example"
        )
    return base, user, pw, site


def _page_options(viewport, site):
    """The page options both helpers share.

    Everything here is pinned rather than inherited from the machine, because a
    published screenshot is compared against its own re-capture: an animation
    caught mid-frame, a locale-dependent number or a different clock offset all
    change bytes without changing meaning, and then a real regression cannot be
    told apart from the noise. The site header is set on the CONTEXT so the login
    POST and every later navigation and XHR carry it — a header applied to only
    some of them would authenticate against one site and render another.
    """
    return {
        "viewport": viewport or {"width": 1440, "height": 900},
        "extra_http_headers": {"X-Frappe-Site-Name": site} if site else None,
        "reduced_motion": "reduce",
        "timezone_id": "UTC",
        "device_scale_factor": 1,
    }


@contextmanager
def anonymous_page(viewport=None):
    """Yield ``(page, base_url)`` for a Playwright page that never logs in.

    The resident-facing web forms are the reason: a logged-in session prefills
    the visitor's own name and email into them, so capturing those pages from the
    authenticated session would publish whoever the screenshot account is. A
    resident meets them signed out, and so does the capture.
    """
    from playwright.sync_api import sync_playwright

    base, _user, _pw, site = _creds()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(**_page_options(viewport, site))
        try:
            yield page, base
        finally:
            browser.close()


@contextmanager
def authenticated_page(viewport=None):
    """Yield ``(page, base_url)`` for a Playwright page logged into the Desk.

    Closes the browser on exit. Raises if the login does not return HTTP 200.
    """
    from playwright.sync_api import sync_playwright

    base, user, pw, site = _creds()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(**_page_options(viewport, site))
        resp = page.request.post(
            f"{base}/api/method/login", form={"usr": user, "pwd": pw}
        )
        if resp.status != 200:
            # Read the body BEFORE closing: closing disposes the response, so the
            # old order raised "Response has been disposed" and threw away the
            # only sentence that says WHY the login was refused.
            detail = f"{resp.status} {resp.text()[:300]}"
            browser.close()
            raise SystemExit(f"Desk login failed: {detail}")
        try:
            yield page, base
        finally:
            browser.close()


def declared_site():
    """The site e2e/.env.local names, or "" when it names none."""
    _load_env()
    return os.environ.get("SITE_NAME") or ""


def assert_site(page, expected):
    """Refuse to continue unless the Desk in ``page`` really is ``expected``.

    Reads the site out of the rendered boot payload, not out of the request the
    caller sent: the header could have been dropped, the page could have been
    opened without it, or a redirect could have re-resolved the host. A capture
    that guesses which site it is looking at can publish another site's rows.
    Call it AFTER the first /app navigation, because frappe.boot only exists once
    the Desk bundle has run.
    """
    actual = page.evaluate("() => (window.frappe && frappe.boot && frappe.boot.sitename) || ''")
    if actual != expected:
        raise SystemExit(f"site mismatch: expected {expected!r}, the Desk reports {actual!r}")
    return actual


def _smoke():
    out = Path(__file__).resolve().parent / "screenshots"
    out.mkdir(exist_ok=True)
    target = out / "operations-control.png"
    with authenticated_page() as (page, base):
        who = page.request.get(f"{base}/api/method/frappe.auth.get_logged_user")
        print("WHOAMI:", who.status, who.text()[:120])
        page.goto(f"{base}/app/operations-control", wait_until="networkidle")
        page.wait_for_timeout(2500)
        print("SITE:", page.evaluate("() => (frappe.boot && frappe.boot.sitename) || '?'"))
        page.screenshot(path=str(target), full_page=True)
    print(f"SAVED {target}")
    return 0


if __name__ == "__main__":
    sys.exit(_smoke())
