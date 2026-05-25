"""Seed the 4 Salis fleet roles. Install-safe and idempotent.

A failure on any single role is logged and skipped so that install/migrate
can never crash because of this seed.
"""

import frappe

# name, desk_access, two_factor, is_custom
# Driver keeps desk_access=1 so the role can hold DocPerms in Desk; the
# self-service portal is gated separately via Salis Settings.enable_driver_portal.
SALIS_ROLES = [
    ("Fleet Manager", 1, 0, 0),
    ("Fleet Project Manager", 1, 0, 0),
    ("Fleet Supervisor", 1, 0, 0),
    ("Driver", 1, 0, 0),
]


def execute():
    for role_name, desk_access, two_factor, is_custom in SALIS_ROLES:
        # Existence-guard — never rely on ignore_if_duplicate.
        if frappe.db.exists("Role", role_name):
            continue
        try:
            doc = frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role_name,
                    "desk_access": desk_access,
                    "two_factor_auth": two_factor,
                    "is_custom": is_custom,
                }
            )
            doc.insert(ignore_permissions=True)  # audit-ok
        except Exception:
            # A seed must NEVER crash install/migrate — log and continue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_roles failed: {role_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
