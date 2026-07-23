# Copyright (c) 2026, AFMCO and contributors
"""Seed the Salis authority-tier roles. Install-safe and idempotent.

A failure on any single role is logged and skipped so that install/migrate
can never crash because of this seed.

Consolidated (v1.x): "Fleet Operations Manager" and "Fleet Regional Manager"
were merged into "Fleet Manager", and "Legal Officer" into
"Government Relations Officer". Those names are intentionally no longer seeded
(omitted from AUTHORITY_ROLES below) so a fresh install never re-creates them.
There is no consolidate_salis_roles patch — the consolidation is enforced purely
by this omission; re-pointing any pre-existing user off an old role name is an
owner decision, not automated.
"""

import frappe

AUTHORITY_ROLES = [
    "Government Relations Officer",
]


def execute():
    for role_name in AUTHORITY_ROLES:
        # [#8xhyiq]
        if frappe.db.exists("Role", role_name):
            continue
        try:
            doc = frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role_name,
                    "desk_access": 1,
                }
            )
            doc.insert(ignore_permissions=True)  # audit-ok
        except Exception:
            # [#kyey4m]
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_authority_roles failed: {role_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
