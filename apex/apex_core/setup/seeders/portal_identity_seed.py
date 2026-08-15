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


def _close_login(email: str) -> None:
    """Disable an identity seeded before login was closed, through the User document.

    The document and not the column, because ``User.check_enable_disable``
    (frappe/core/doctype/user/user.py:273-280) is what logs the account's live sessions
    out; a raw write leaves an already-open session valid. Nothing to do when the row is
    already closed, so a migrate on a current site costs one read.
    """
    if not frappe.db.get_value("User", email, "enabled"):
        return
    user = frappe.get_doc("User", email)
    user.enabled = 0
    user.save()


def seed_portal_identities() -> None:
    """Create the two capacity users, idempotently, with login closed.

    ``enabled: 0`` is what actually closes the door: frappe/auth.py:274-277 refuses a
    login for a user that is not enabled and frappe/auth.py:707 refuses its API key the
    same way. ``simultaneous_sessions``, which this used to zero, gates neither — it is
    read as ``... or 1`` (frappe/sessions.py:66) and only caps concurrent sessions, so
    zero meant one. No password is set either, so there is nothing to authenticate
    against in the first place.

    ``frappe.set_user`` never consults ``enabled`` (frappe/__init__.py:641 only rewrites
    ``frappe.local.session``), so ``as_capacity`` still reaches the identity, and
    ``frappe.permissions.get_roles`` reads Has Role without an enabled filter, so the
    DocPerms still grade the portal write.

    An identity seeded before this converges on the next migrate rather than being
    skipped: this runs from after_migrate, and an existing enabled row would otherwise
    stay open forever.
    """
    for email, role, first_name, last_name in CAPACITIES:
        _ensure_role(role)
        if frappe.db.exists("User", email):
            _close_login(email)
            continue
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "user_type": "System User",
            "enabled": 0,
            "send_welcome_email": 0,
            "roles": [{"role": role}],
        })
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
