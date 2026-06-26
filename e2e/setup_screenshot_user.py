"""Idempotent setup of the screenshot-bot Desk user on the `test` bench.

Run through bench console so a Playwright session can authenticate to the Desk
and capture visual evidence (the show-fixed-pages Evidence Contract) WITHOUT
set-admin-password. Re-runnable: re-uses an existing user/role grant and only
resets the password. NOT a hooks-registered patch on purpose — this is a
test-bench-only screenshot account, never provisioned on a real site.

Credential source: env (loaded from e2e/.env.local, which is GITIGNORED). The
password is never hardcoded here. From the bench root, source the cred then run
the file as ONE compiled unit (do NOT pipe it line-by-line — bench console feeds
stdin cell-by-cell and breaks indented if/else blocks with NameError):

    set -a; . <apex>/e2e/.env.local; set +a
    p='<apex>/e2e/setup_screenshot_user.py'
    echo "exec(compile(open('$p').read(),'$p','exec'),{'__name__':'setup'})" \\
        | bench --site test console

Roles are read-only Desk roles needed to VIEW the operator pages; the account
gets no write/submit grant of its own.
"""
import os

import frappe

# Read-only Desk roles that gate the operator pages a screenshot targets
# (e.g. /app/operations-control "Fleet Control", and the housing desks).
_DESK_ROLES = [
    "Fleet Manager",
    "Fleet Supervisor",
    "Accommodation Manager",
    "Resident Supervisor",
]

_email = os.environ.get("SCREENSHOT_USER")
_pw = os.environ.get("SCREENSHOT_PW")
if not _email or not _pw:
    raise SystemExit("SCREENSHOT_USER / SCREENSHOT_PW not set — source e2e/.env.local first")

if not frappe.db.exists("User", _email):
    _u = frappe.get_doc({
        "doctype": "User",
        "email": _email,
        "first_name": "Screenshot",
        "last_name": "Bot",
        "user_type": "System User",
        "send_welcome_email": 0,
    })
    _u.insert(ignore_permissions=True)
    _action = "created"
else:
    _u = frappe.get_doc("User", _email)
    _action = "reused"

_missing = [r for r in _DESK_ROLES if r not in frappe.get_roles(_email) and frappe.db.exists("Role", r)]
if _missing:
    _u.add_roles(*_missing)

# Keep login enabled and the password in sync with the env cred on every run.
_u.enabled = 1
_u.new_password = _pw
_u.save(ignore_permissions=True)
frappe.db.commit()

print(f"screenshot user {_action}: {_email}")
print(f"roles: {sorted(frappe.get_roles(_email))}")
