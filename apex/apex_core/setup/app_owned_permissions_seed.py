# Copyright (c) 2026, afmcoltd

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
