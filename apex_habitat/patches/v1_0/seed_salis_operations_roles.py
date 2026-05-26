"""Seed the Salis Operations-side approval-tier roles. Install-safe and idempotent.

These roles back the Operations authority ladder used by Transport Request DoA
(Project Manager < Regional Operations Manager < Operations Manager). Some of
these roles may already be provisioned by ERPNext/HRMS; the existence guard
skips them cleanly. A failure on any single role is logged and skipped so that
install/migrate can never crash because of this seed.
"""

import frappe

# name, authority_tier (documentation only — not a Role field)
OPERATIONS_ROLES = [
    ("Project Manager", "TIER_PROJECT"),
    ("Regional Operations Manager", "TIER_REGIONAL_OPS"),
    ("Operations Manager", "TIER_OPERATIONS"),
]


def execute():
    for role_name, _authority_tier in OPERATIONS_ROLES:
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
                title=f"seed_salis_operations_roles failed: {role_name}",
                message=frappe.get_traceback(),
            )

    frappe.db.commit()
