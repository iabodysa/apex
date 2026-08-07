# Copyright (c) 2026, AFMCO and contributors
"""Seed the Salis fleet roles. Install-safe, idempotent, existence-guarded.

These lived in ``patches/v1_0/seed_salis_roles.py`` and
``seed_salis_authority_roles.py``, and ``salis/setup.py`` imported both to run them at
install time — the only import of ``apex.patches`` anywhere in the app. A patch is a
one-time migration for sites that already exist; it is the wrong home for data every
NEW site needs, and the import made retiring those patches an ImportError on first
install rather than the harmless cleanup it looks like.

Three of these five are provided by nothing else — Fleet Project Manager, Fleet
Supervisor and Government Relations Officer are absent from ``apex.setup.create_roles``,
so without this seeder a fresh install has no fleet supervision roles at all. The other
two are carried here anyway so the seeder is self-contained: a list that only makes sense
when read against another module's list is the arrangement that let this gap open.

Two names are deliberately ABSENT and must stay absent. ``Fleet Operations Manager`` and
``Fleet Regional Manager`` were consolidated into ``Fleet Manager``, and ``Legal
Officer`` into ``Government Relations Officer``. There is no un-consolidation patch: the
consolidation is enforced purely by their omission here, so re-adding either name
silently reverses an owner decision. Re-pointing an existing user off a retired name is
the owner's call, never automatic.
"""

import frappe

SALIS_ROLES = [
    ("Fleet Manager", 1),
    ("Fleet Project Manager", 1),
    ("Fleet Supervisor", 1),
    ("Government Relations Officer", 1),
    ("Driver", 0),
]


def seed_salis_roles():
    """Create any missing Salis role. Returns the names created on this call."""
    created = []
    for role_name, desk_access in SALIS_ROLES:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.db.savepoint("salis_role")
        try:
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role_name,
                    "desk_access": desk_access,
                    "two_factor_auth": 0,
                    "is_custom": 0,
                }
            ).insert(ignore_permissions=True)  # audit-ok: install-time seed, no user session
            created.append(role_name)
        except Exception:
            frappe.db.rollback(save_point="salis_role")
            frappe.log_error(
                title=f"salis_roles_seed failed: {role_name}",
                message=frappe.get_traceback(),
            )
    return created
