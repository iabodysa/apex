"""Seed the Salis governance authority-tier roles. Install-safe and idempotent.

A failure on any single role is logged and skipped so that install/migrate
can never crash because of this seed.
"""

import frappe

# name, authority_tier (documentation only — not a Role field)
GOVERNANCE_ROLES = [
    ("Fleet Operations Manager", "TIER_OPERATIONS"),
    ("Fleet Regional Manager", "REG"),
    ("Government Relations Officer", None),
    ("Legal Officer", None),
]


def execute():
    for role_name, _authority_tier in GOVERNANCE_ROLES:
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
