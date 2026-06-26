"""Playwright Desk-auth helper — log a screenshot session into the Frappe Desk.

WHY: visual evidence (the show-fixed-pages Evidence Contract) needs an
authenticated, NON-Guest Desk session. This helper reads a synthetic
screenshot-bot credential from the environment (never inline) and establishes
the Frappe session cookie, so a task can then goto /app/<page> and screenshot it.

CRED LOCATION (gitignored): e2e/.env.local  — keys BASE_URL, SCREENSHOT_USER,
SCREENSHOT_PW. A committed template lives at e2e/.env.local.example. The
matching Desk user is provisioned idempotently by e2e/setup_screenshot_user.py.

ONE-TIME SETUP (bench root) — run the setup file as ONE compiled unit; do NOT
pipe it line-by-line (bench console feeds stdin cell-by-cell and breaks if/else):
    cp e2e/.env.local.example e2e/.env.local   # then edit SCREENSHOT_PW
    set -a; . <apex>/e2e/.env.local; set +a
    p='<apex>/e2e/setup_screenshot_user.py'
    echo "exec(compile(open('$p').read(),'$p','exec'),{'__name__':'setup'})" | bench --site test console

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
    if not user or not pw:
        raise SystemExit(
            "SCREENSHOT_USER / SCREENSHOT_PW not set — create e2e/.env.local "
            "from e2e/.env.local.example"
        )
    return base, user, pw


@contextmanager
def authenticated_page(viewport=None):
    """Yield ``(page, base_url)`` for a Playwright page logged into the Desk.

    Closes the browser on exit. Raises if the login does not return HTTP 200.
    """
    from playwright.sync_api import sync_playwright

    base, user, pw = _creds()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport or {"width": 1440, "height": 900})
        resp = page.request.post(
            f"{base}/api/method/login", form={"usr": user, "pwd": pw}
        )
        if resp.status != 200:
            browser.close()
            raise SystemExit(f"Desk login failed: {resp.status} {resp.text()[:200]}")
        try:
            yield page, base
        finally:
            browser.close()


def _smoke():
    out = Path(__file__).resolve().parent / "screenshots"
    out.mkdir(exist_ok=True)
    target = out / "operations-control.png"
    with authenticated_page() as (page, base):
        who = page.request.get(f"{base}/api/method/frappe.auth.get_logged_user")
        print("WHOAMI:", who.status, who.text()[:120])
        page.goto(f"{base}/app/operations-control", wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(target), full_page=True)
    print(f"SAVED {target}")
    return 0


if __name__ == "__main__":
    sys.exit(_smoke())
