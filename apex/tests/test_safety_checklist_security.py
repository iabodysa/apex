# Copyright (c) 2026, AFMCO and contributors
"""Security and permission tests for the Safety Checklist API."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.api.safety_checklist import submit_round
from apex.tests._helpers import _user
from apex.tests.factories import make_building, make_company


class TestSafetyChecklistSecurity(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        make_company()
        self.building_allowed = make_building(name=f"Sec Bldg Allowed {tag}").name
        self.building_forbidden = make_building(name=f"Sec Bldg Forbidden {tag}").name

        # [#2hgqvb]
        self.user_email = f"supervisor-{tag}@example.com".lower()
        _user(self.user_email, "Resident Supervisor")

        # [#pp24wc]
        if not frappe.db.exists(
            "User Permission",
            {"user": self.user_email, "allow": "Building", "for_value": self.building_allowed},
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": self.user_email,
                    "allow": "Building",
                    "for_value": self.building_allowed,
                }
            ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_submit_round_throws_without_permission(self):
        frappe.set_user(self.user_email)

        # [#sj0zz6]
        lines = []

        with self.assertRaises(frappe.PermissionError):
            submit_round(
                building=self.building_forbidden,
                cadence="Daily",
                round_date=today(),
                lines=lines,
            )


def tearDownModule():
    # A raw commit anywhere in the suite persists these Buildings past
    # FrappeTestCase rollback; drop every Building created after the baseline (P-148).
    from apex.tests import factories

    factories.purge_test_buildings()
