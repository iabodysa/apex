# Copyright (c) 2026, AFMCO and contributors
"""Seed the 4 Salis fleet roles. Install-safe and idempotent.

A failure on any single role is logged and skipped so that install/migrate
can never crash because of this seed.
"""

import frappe

# [#6g22it]
SALIS_ROLES = [
    ("Fleet Manager", 1, 0, 0),
    ("Fleet Project Manager", 1, 0, 0),
    ("Fleet Supervisor", 1, 0, 0),
    # Driver is a field worker: desk_access=0 (native Website User isolation). Kept in
    # step with setup.create_roles, which also seeds Driver at desk_access=0 first.
    ("Driver", 0, 0, 0),
]


def execute():
    for role_name, desk_access, two_factor, is_custom in SALIS_ROLES:
        # [#8xhyiq]
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
            # [#kyey4m]
            frappe.db.rollback()
            frappe.log_error(
                title=f"seed_salis_roles failed: {role_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
