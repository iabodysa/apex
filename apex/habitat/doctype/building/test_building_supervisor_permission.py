# Copyright (c) 2026, AFMCO and contributors
"""The building's responsible_supervisor is the single source of truth for
the building-scoped User Permission — on_update keeps the permission in sync.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building


def _user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@")[0],
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    return email


def _has_perm(user, building):
    return bool(
        frappe.db.exists(
            "User Permission",
            {"user": user, "allow": "Building", "for_value": building},
        )
    )


class TestBuildingSupervisorPermission(FrappeTestCase):
    def test_supervisor_field_syncs_user_permission(self):
        frappe.set_user("Administrator")
        sup_a = _user("t254_sup_a@example.com")
        sup_b = _user("t254_sup_b@example.com")
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        b = make_building(
            name="T254 Building", company=company, responsible_supervisor=sup_a
        )
        self.assertTrue(_has_perm(sup_a, b.name))

        b.responsible_supervisor = sup_b
        b.save(ignore_permissions=True)
        self.assertFalse(_has_perm(sup_a, b.name))
        self.assertTrue(_has_perm(sup_b, b.name))

        b.responsible_supervisor = None
        b.save(ignore_permissions=True)
        self.assertFalse(_has_perm(sup_b, b.name))
