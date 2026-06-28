# Copyright (c) 2026, AFMCO and contributors
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


def _project(project_name="QA Scope Project"):
    """Return a Project named ``project_name``, creating it if absent. Idempotent.
    Used to give a scoped Salis user a tenant to be permitted for."""
    existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    if existing:
        return existing
    return frappe.get_doc(
        {"doctype": "Project", "project_name": project_name}
    ).insert(ignore_permissions=True).name


def _grant_project(user, project):
    """Grant ``user`` a Project User Permission for ``project`` (idempotent), so the
    project-scoped Salis permission hooks admit the user's in-scope rows."""
    if not frappe.db.exists(
        "User Permission", {"user": user, "allow": "Project", "for_value": project}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": "Project",
                "for_value": project,
            }
        ).insert(ignore_permissions=True)
