# Copyright (c) 2026, afmcoltd
"""One identity per portal CAPACITY, so a portal write can carry a role instead of a bypass.

A worker and a driver reach Apex by token. Neither is a Frappe user and neither is meant to become
one — the owner ruled that directly. Every write below runs only from ``seed_portal_identities``,
reached from ``apex/setup.py``'s ``after_install``/``after_migrate`` or from the one-time
``setup_wizard_complete`` flow, so the acting user is always Administrator, who already carries
every permission (frappe/permissions.py:107,273,506).

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

Blocked from a fixture by the gap-filler property: an existing identity is converged, not
replaced — ``_close_login`` and ``_grant_role`` touch only the field or role a migration
requires, leaving the rest of the record as an operator left it. A fixture-shipped User or
Role is instead deleted and reinserted whole on every migrate (frappe/modules/import_file.py:
230-239, forced by frappe/utils/fixtures.py:41), which would erase that.
"""

import frappe

WORKER_USER = "worker@apex.internal"
DRIVER_USER = "driver@apex.internal"
WORKER_ROLE = "Worker"
DRIVER_ROLE = "Driver"

WORKER_CAPACITY_ROLE = "Portal Worker Capacity"
DRIVER_CAPACITY_ROLE = "Portal Driver Capacity"

CAPACITIES = (
    (WORKER_USER, WORKER_ROLE, WORKER_CAPACITY_ROLE, "Worker", "Portal"),
    (DRIVER_USER, DRIVER_ROLE, DRIVER_CAPACITY_ROLE, "Driver", "Portal"),
)

def _ensure_role(role: str) -> None:
    """A capacity needs a role before it can hold one."""
    if not frappe.db.exists("Role", role):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role,
            "desk_access": 0,
        }).insert()

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

def _grant_role(email: str, role: str) -> None:
    """Add ``role`` to an already-seeded identity, once.

    The insert branch below names every role at creation, so this reaches only an
    identity seeded before that role existed. Without it a site that already carries the
    two capacity users would never gain the capacity role, and every portal write would
    fail its DocPerm on the next migrate rather than on a fresh install — the failure
    mode that hides until an upgrade.
    """
    if frappe.db.exists("Has Role", {"parent": email, "parenttype": "User", "role": role}):
        return
    user = frappe.get_doc("User", email)
    user.append("roles", {"role": role})
    user.save()

def seed_portal_identities() -> None:
    """Create the two capacity users, idempotently, with login closed.

    ``enabled: 0`` is what actually closes the door: frappe/auth.py:274-277 refuses a
    login for a user that is not enabled and frappe/auth.py:707 refuses its API key the
    same way. ``simultaneous_sessions`` gates neither login path — it is read as
    ``... or 1`` (frappe/sessions.py:66) and only caps concurrent sessions, so a zero
    value still permits one. No password is set either, so there is nothing to
    authenticate against in the first place.

    ``frappe.set_user`` never consults ``enabled`` (frappe/__init__.py:641 only rewrites
    ``frappe.local.session``), so ``as_capacity`` still reaches the identity, and
    ``frappe.permissions.get_roles`` reads Has Role without an enabled filter, so the
    DocPerms still grade the portal write.

    An identity seeded before this converges rather than being skipped: this runs from
    both after_install and after_migrate, and an existing enabled row would otherwise
    stay open forever.

    ``user_type`` is deliberately absent from the insert: ``User.set_system_user``
    (frappe/core/doctype/user/user.py:303-314) overwrites it on every validate, deriving
    it from the desk_access of the roles held. Naming a value here would state one thing
    while the record became another.

    ``frappe.is_setup_complete`` gates the whole function, so on a fresh install this
    returns before creating anything and the two identities do not exist until the setup
    wizard has run. Nothing is left open by that: ``create_roles`` has already shipped
    both capacity roles with ``desk_access`` 0, and ``User.set_system_user`` derives
    ``user_type`` from the desk_access of the roles a user holds, so whenever these
    identities are finally created they are born Website Users.
    """
    if not frappe.is_setup_complete():
        return

    for email, role, capacity_role, first_name, last_name in CAPACITIES:
        _ensure_role(role)
        _ensure_role(capacity_role)
        if frappe.db.exists("User", email):
            _close_login(email)
            _grant_role(email, capacity_role)
            continue
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "enabled": 0,
            "send_welcome_email": 0,
            "roles": [{"role": role}, {"role": capacity_role}],
        })
        user.flags.no_welcome_mail = True
        user.insert()
