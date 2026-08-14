# Copyright (c) 2026, afmcoltd
"""One identity per portal CAPACITY, so a portal write can carry a role instead of a bypass.

A worker and a driver reach Apex by token. Neither is a Frappe user and neither is meant to become
one — the owner ruled that directly. But a write with no user has no roles to consult, which is why
every portal endpoint passed ``ignore_permissions``: there was nothing for a DocPerm to attach to.

The identity these seed is per CAPACITY, not per person: two users, `worker` and `driver`. The
token already carries WHO — it resolves to an Employee — so the user only has to carry WHAT THAT
CAPACITY MAY DO. One user per worker would build a second copy of the Employee table that has to be
kept in step, for no gain.

Both are login-disabled and hold no password, so neither can authenticate from outside. They are
reachable only through ``frappe.set_user`` after a token has already been verified, which is what
makes them an identity without a door.

The consequence to know: ``owner`` on a portal-written record becomes the capacity user rather than
a person. Scoping must therefore come from the record's own ``employee`` field, which is where the
portal reads it from today — checked before this landed, and one place in the portal reads ``owner``
at all (``masar_worker.py:254``), which reads a Custody Issue a storekeeper creates.
"""

import frappe

WORKER_USER = "worker@apex.internal"
DRIVER_USER = "driver@apex.internal"
WORKER_ROLE = "Worker"
DRIVER_ROLE = "Driver"

CAPACITIES = (
    (WORKER_USER, WORKER_ROLE, "Worker", "Portal"),
    (DRIVER_USER, DRIVER_ROLE, "Driver", "Portal"),
)


def _ensure_role(role: str) -> None:
    """A capacity needs a role before it can hold one."""
    if not frappe.db.exists("Role", role):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role,
            "desk_access": 0,
        }).insert(ignore_permissions=True)


def seed_portal_identities() -> None:
    """Create the two capacity users, idempotently, with login closed."""
    for email, role, first_name, last_name in CAPACITIES:
        _ensure_role(role)
        if frappe.db.exists("User", email):
            continue
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": role}],
        })
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
        # No password is ever set, so the account cannot be authenticated against.
        frappe.db.set_value("User", email, "simultaneous_sessions", 0)
