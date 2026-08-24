# Copyright (c) 2026, afmcoltd
"""Retire the two Apex roles nothing ever wired up, and close Admin Manager's empty desk.

``apex.setup.create_roles`` created fifteen roles with ``desk_access=1``. Three of them
carry no DocPerm on any Apex DocType, appear in no Role Profile, and are read by no
controller or client script: Operations Director, Facilities Supervisor, Admin Manager.
Granting any of the three signed an operator into a desk with nothing on it.

Operations Director and Facilities Supervisor are pure dead weight — nothing in the tree
or the database points at them — so this patch removes both. Admin Manager is different:
Building License's ``responsible_role`` field defaults to it and two live rows name it, so
the role stays; only its desk access is switched off, since naming a role on a document
never required a desk.

A blocked deletion is PRINTED rather than logged: ``frappe.logger().info`` emits on no site,
because ``frappe/utils/logger.py:12`` defaults the level to WARNING on a dev server and ERROR
otherwise and nothing sets it lower, while migrate's own output is what the operator running
the upgrade is reading.
"""

import frappe

DEAD_ROLES = ("Operations Director", "Facilities Supervisor")


def execute():
    """Deletes the two dead roles where nothing blocks it, and closes Admin Manager's desk."""
    for role_name in DEAD_ROLES:
        if not frappe.db.exists("Role", role_name):
            continue
        try:
            frappe.delete_doc("Role", role_name)
        except frappe.LinkExistsError as e:
            print(f"apex: Role {role_name} is still referenced and was left in place: {e}")

    if frappe.db.exists("Role", "Admin Manager"):
        frappe.db.set_value("Role", "Admin Manager", "desk_access", 0)
