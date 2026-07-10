# Copyright (c) 2026, AFMCO and contributors
"""ONE-TIME cleanup (T-668): drop the "System Manager" role from the existing
"Habitat Accommodation Manager" Role Profile on already-provisioned sites.

The profile previously bundled System Manager with Accommodation Manager, which
granted every Accommodation Manager full administrative rights (privilege
escalation). create_role_profiles() was corrected to seed only the functional
role, but that fix only covers FRESH installs / new profiles — the create path
never rewrites an existing Role Profile's child rows. This removes the stale
System Manager row from any site that already has the profile.

Safety / idempotency:
- No-op if the Role Profile does not exist or has no System Manager row.
- Removes only the System Manager child row; the Accommodation Manager role and
  any other rows are preserved.
- Safe to re-run (becomes a no-op once the row is gone) and a no-op on fresh
  installs (the profile is seeded without System Manager from the start).

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe

_PROFILE = "Habitat Accommodation Manager"
_ROLE = "System Manager"


def execute():
    if not frappe.db.exists("Role Profile", _PROFILE):
        return

    profile = frappe.get_doc("Role Profile", _PROFILE)
    kept = [row for row in profile.roles if row.role != _ROLE]
    if len(kept) == len(profile.roles):
        return  # [#hedo5n]

    profile.set("roles", kept)
    profile.save(ignore_permissions=True)  # audit-ok: one-time admin cleanup patch
    frappe.logger().info(
        f"drop_sysmgr_from_accommodation_manager_profile: removed {_ROLE} from {_PROFILE}"
    )
