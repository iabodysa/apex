"""Idempotent setup of the screenshot-bot Desk user on the `test` bench.

Run through bench console so a Playwright session can authenticate to the Desk
and capture screenshots of the operator pages WITHOUT set-admin-password.
Re-runnable, and DECLARATIVE about roles: a re-run brings the account back to
exactly the roles listed below — it grants the missing ones AND revokes any role
granted outside this file. It also resets the password on every run.
NOT a hooks-registered patch on purpose — this is a test-bench-only screenshot
account, never provisioned on a real site.

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

SYSTEM MANAGER — DECIDED: NOT GRANTED, and the reconciliation below actively
revokes it. Every page in the current capture set is reachable without it: the
Fleet Control Desk page grants Fleet Manager / Fleet Project Manager / Fleet
Supervisor (apex/salis/page/operations_control/operations_control.json), and the
Habitat and Salis root Workspaces grant Accommodation Manager / Resident
Supervisor and Fleet Manager / Fleet Supervisor respectively. System Manager is a
superuser role, so holding it makes every spec that authenticates as this account
blind to exactly the permission regressions the account is shaped to catch — it
had drifted onto the live account and already misled one diagnosis. If some future
capture genuinely needs a superuser view (Role Permission Manager, System
Settings), give that capture its OWN declared account rather than widening this
one, so the other specs do not silently upgrade alongside it.
"""
import os

import frappe

# Read-only Desk roles that gate the operator pages a screenshot targets
# (e.g. /app/operations-control "Fleet Control", and the housing desks).
# This list is the WHOLE grant, not a minimum — see the note in the docstring.
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

# Reconcile the Has Role rows in BOTH directions. An additive-only setup let the
# live account drift onto System Manager, so every spec silently ran as a superuser
# and a permission regression that would block a real supervisor passed unnoticed.
# The automatic roles (All / Guest / Desk User) are never stored here, so this
# cannot strip them: frappe.get_roles appends them synthetically (permissions.py).
_declared = [r for r in _DESK_ROLES if frappe.db.exists("Role", r)]
_before = sorted(d.role for d in _u.get("roles"))
for _row in list(_u.get("roles")):
    if _row.role not in _declared:
        _u.get("roles").remove(_row)
_u.append_roles(*_declared)
_after = sorted(d.role for d in _u.get("roles"))
_revoked = sorted(set(_before) - set(_after))

# Keep login enabled and the password in sync with the env cred on every run.
_u.enabled = 1
_u.new_password = _pw
_u.save(ignore_permissions=True)
frappe.db.commit()

print(f"screenshot user {_action}: {_email}")
print(f"declared roles: {sorted(_declared)}")
print(f"granted roles: {sorted(d.role for d in frappe.get_doc('User', _email).get('roles'))}")
print(f"revoked (granted outside this file): {_revoked}")
