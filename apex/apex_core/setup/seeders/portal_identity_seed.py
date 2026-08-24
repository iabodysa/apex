# Copyright (c) 2026, afmcoltd

import frappe

WORKER_USER = "worker@apex.internal"
DRIVER_USER = "driver@apex.internal"
WORKER_ROLE = "Worker"
DRIVER_ROLE = "Driver"

WORKER_CAPACITY_ROLE = "Portal Worker Capacity"
DRIVER_CAPACITY_ROLE = "Portal Driver Capacity"

CAPACITIES = (
    (WORKER_USER, WORKER_ROLE, WORKER_CAPACITY_ROLE, "Worker", "Portal"),
    (DRIVER_USER, DRIVER_ROLE, DRIVER_CAPACITY_ROLE, "Driver", "Portal"),
)

def _ensure_role(role: str) -> None:
    if not frappe.db.exists("Role", role):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": role,
            "desk_access": 0,
        }).insert()

def _close_login(email: str) -> None:
    if not frappe.db.get_value("User", email, "enabled"):
        return
    user = frappe.get_doc("User", email)
    user.enabled = 0
    user.save()

def _grant_role(email: str, role: str) -> None:
    if frappe.db.exists("Has Role", {"parent": email, "parenttype": "User", "role": role}):
        return
    user = frappe.get_doc("User", email)
    user.append("roles", {"role": role})
    user.save()

def seed_portal_identities() -> None:
    if not frappe.is_setup_complete():
        return

    for email, role, capacity_role, first_name, last_name in CAPACITIES:
        _ensure_role(role)
        _ensure_role(capacity_role)
        if frappe.db.exists("User", email):
            _close_login(email)
            _grant_role(email, capacity_role)
            continue
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "enabled": 0,
            "send_welcome_email": 0,
            "roles": [{"role": role}, {"role": capacity_role}],
        })
        user.flags.no_welcome_mail = True
        user.insert()
