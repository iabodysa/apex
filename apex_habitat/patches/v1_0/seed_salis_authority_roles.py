"""Seed the Salis authority-tier roles. Install-safe and idempotent.

A failure on any single role is logged and skipped so that install/migrate
can never crash because of this seed.

Consolidated (v1.x): "Fleet Operations Manager" and "Fleet Regional Manager"
were merged into "Fleet Manager", and "Legal Officer" into
"Government Relations Officer" (see patches/v1_x/consolidate_salis_roles.py).
Those names are intentionally no longer seeded so they are not re-created.
"""

import frappe

AUTHORITY_ROLES = [
    "Government Relations Officer",
]


def execute():
    for role_name in AUTHORITY_ROLES:
        # Existence-guard — never rely on ignore_if_duplicate.
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
            # A seed must NEVER crash install/migrate — log and continue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_authority_roles failed: {role_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
