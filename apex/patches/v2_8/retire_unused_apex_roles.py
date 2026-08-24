# Copyright (c) 2026, afmcoltd

import frappe

DEAD_ROLES = ("Operations Director", "Facilities Supervisor")


def execute():
    for role_name in DEAD_ROLES:
        if not frappe.db.exists("Role", role_name):
            continue
        try:
            frappe.delete_doc("Role", role_name)
        except frappe.LinkExistsError as e:
            print(f"apex: Role {role_name} is still referenced and was left in place: {e}")

    if frappe.db.exists("Role", "Admin Manager"):
        frappe.db.set_value("Role", "Admin Manager", "desk_access", 0)
