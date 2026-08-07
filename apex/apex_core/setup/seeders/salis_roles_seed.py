# Copyright (c) 2026, AFMCO and contributors
"""Turn desk access OFF for the portal-only Salis roles.

THIS DOES NOT CREATE ROLES, and an earlier version of this file that did was wrong.
Frappe makes a Role record for every role named in a shipped DocType's ``permissions``
block: ``make_module_and_roles`` in ``frappe/core/doctype/doctype/doctype.py:1852``, whose
own docstring reads "Make `Module Def` and `Role` records if already not made. Called
while installing." Fleet Manager, Fleet Project Manager, Fleet Supervisor, Government
Relations Officer and Driver each appear in shipped DocPerm rows, so all five arrive with
the DocTypes and a seeder that creates them is dead code — verified on a clean site.

What the framework does not get right is desk access: ``make_module_and_roles`` inserts
every role with ``desk_access = 1``. Driver is portal-only — a driver reaches /driver with
a token and never signs in to the desk — so it is turned off here. That is exactly what
ERPNext does for its own website roles (``erpnext/setup/install.py:287-290``).

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
