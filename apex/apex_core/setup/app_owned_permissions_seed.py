# Copyright (c) 2026, afmcoltd
"""Grant Apex's own permissions on DocTypes it does not own.

Employee, Cost Center and Project belong to hrms and erpnext; Activity Log and
Notification Log belong to frappe. Apex needs a handful of extra grants on each, and
Employee/Cost Center/Project's rows travelled in the ``custom_perms`` block of
``apex/habitat/custom/*.json`` until now.

Why that mechanism had to go: ``modules/utils.py:182-187`` DELETES every Custom DocPerm
row of the DocType and reinserts only the file's, on every migrate. So a row an
administrator adds through Role Permission Manager is gone at the next update, silently —
measured, not reasoned: a row added on a live site took Employee from 7 to 8, and one
``bench migrate`` exiting 0 returned it to 7 with the added row missing.

Why dropping the block is safe: Custom DocPerm is all-or-nothing per DocType.
``Meta.set_custom_permissions`` (frappe/model/meta.py:541-552) replaces the shipped
permissions block ONLY when at least one Custom DocPerm row exists — ``if custom_perms:``
at :552 — so zero rows leaves the owning app's standard DocPerm in force. That standard
block is present and carries the base roles, HR Manager among them.

Why only SIXTEEN rows are seeded and not the twenty-nine that were exported: thirteen of
the exported rows are copies of the base apps' own DocPerm — same role, same permlevel,
flag for flag. Seeding those would rebuild the duplication this change removes, and they
are already in force through the fallback above.

THE TRAP THIS FILE EXISTS TO AVOID: THIRTEEN of the sixteen grant ``select`` and NOTHING
else — the Link-field picker, so a supervisor can choose an Employee without being able
to open one. ``frappe.permissions.add_permission`` grants ``read`` by default, so seeding
these with its default would hand thirteen roles read access to personnel, cost and project
records they cannot see today. Every row below therefore names its own permission types
and ``read`` is set only where the file set it.

Activity Log and Notification Log rows are CREATE-only for the same trap: both DocTypes
carry an operator-written audit or alert row naming a SUBJECT distinct from the actor
(``portal_identity.log_credential_event``, ``system_notify.notify_user_system``), so the
acting role never needs to read what it just wrote. Each row here REPEATS a pre-existing
native ``read`` (System Manager on Activity Log, ``All`` on Notification Log) alongside
the new ``create``, so seeding it does not drop that native grant.

CONTRACT: this runs at install AND at migrate, and is guarded per row, so it is safe to
re-run and never overwrites a row an operator has adjusted.
"""

from __future__ import annotations

import frappe
from frappe.permissions import add_permission, update_permission_property

APP_OWNED_PERMISSIONS = (
    ("Employee", "Employee Self Service", 0, ("read", "write", "export", "share", "print", "email")),
    ("Employee", "Accommodation Manager", 0, ("select",)),
    ("Employee", "Resident Supervisor", 0, ("select",)),
    ("Employee", "Internal Auditor", 0, ("select",)),
    ("Cost Center", "Employee Self Service", 0, ("select", "export")),
    ("Cost Center", "Accommodation Manager", 0, ("select",)),
    ("Cost Center", "Resident Supervisor", 0, ("select",)),
    ("Cost Center", "Internal Auditor", 0, ("select",)),
    ("Project", "Employee Self Service", 0, ("select", "export")),
    ("Project", "Accommodation Manager", 0, ("select",)),
    ("Project", "Resident Supervisor", 0, ("select",)),
    ("Project", "Internal Auditor", 0, ("select",)),
    ("Project", "Fleet Manager", 0, ("select",)),
    ("Project", "Fleet Project Manager", 0, ("select",)),
    ("Project", "Fleet Supervisor", 0, ("select",)),
    ("Project", "Finance Manager", 0, ("select",)),
    ("Issue", "Portal Driver Capacity", 0, ("create",)),
    ("Activity Log", "System Manager", 0, ("read", "create")),
    ("Activity Log", "Accommodation Manager", 0, ("create",)),
    ("Activity Log", "Resident Supervisor", 0, ("create",)),
    ("Activity Log", "Fleet Project Manager", 0, ("create",)),
    ("Activity Log", "Fleet Supervisor", 0, ("create",)),
    ("Activity Log", "Fleet Manager", 0, ("create",)),
    ("Activity Log", "HR User", 0, ("create",)),
    ("Activity Log", "HR Manager", 0, ("create",)),
    ("Notification Log", "All", 0, ("read", "create")),
    ("Material Request", "SIM Operations User", 0, ("create",)),
    ("Payment Entry", "SIM Operations User", 0, ("create",)),
)

_ALL_PTYPES = (
    "select", "read", "write", "create", "delete", "submit", "cancel", "amend",
    "report", "export", "import", "share", "print", "email",
)


def seed_app_owned_permissions():
    """Create the rows this app needs, leaving every other Custom DocPerm alone."""
    for doctype, role, permlevel, granted in APP_OWNED_PERMISSIONS:
        if not frappe.db.exists("DocType", doctype):
            continue
        if not frappe.db.exists("Role", role):
            continue
        if frappe.db.exists(
            "Custom DocPerm", {"parent": doctype, "role": role, "permlevel": permlevel}
        ):
            continue

        add_permission(doctype, role, permlevel=permlevel, ptype=granted[0])
        for ptype in _ALL_PTYPES:
            if ptype == granted[0]:
                continue
            update_permission_property(
                doctype, role, permlevel, ptype, 1 if ptype in granted else 0
            )
