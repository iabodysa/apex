# Copyright (c) 2026, afmcoltd
"""Turn desk access OFF for the portal-only Salis roles.

SET, never created: this corrects the role the framework already made rather than racing
it. The old create-if-missing version could not have fixed desk access even in principle,
because the DocType import runs first and its existence guard then skipped every role.
"""

import frappe

PORTAL_ONLY_ROLES = ("Driver",)


def seed_salis_roles():
    """Clear desk access on the portal-only roles. Returns the names changed."""
    changed = []
    for role in PORTAL_ONLY_ROLES:
        if not frappe.db.exists("Role", role):
            continue
        if frappe.db.get_value("Role", role, "desk_access"):
            frappe.db.set_value("Role", role, "desk_access", 0)
            changed.append(role)
    return changed
