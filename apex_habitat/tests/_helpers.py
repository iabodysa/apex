"""Shared test helpers for the Salis test suite."""

import frappe


def _user(email, role):
    """Return a User with ``email``, creating it if needed, and ensure it holds
    ``role``. Idempotent: re-uses an existing user/role grant."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email,
                            "first_name": email.split("@")[0], "send_welcome_email": 0})
        u.insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if role not in frappe.get_roles(email):
        u.add_roles(role)
    return email
