# Copyright (c) 2026, AFMCO and contributors
"""Security and permission tests for the Safety Checklist API."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.habitat.api.safety_checklist import submit_round
from apex_habitat.tests._helpers import _user
from apex_habitat.tests.factories import make_building, make_company


class TestSafetyChecklistSecurity(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        make_company()
        self.building_allowed = make_building(name=f"Sec Bldg Allowed {tag}").name
        self.building_forbidden = make_building(name=f"Sec Bldg Forbidden {tag}").name

        # Create a user with Resident Supervisor role (has submit permission on Safety Task Execution)
        self.user_email = f"supervisor-{tag}@example.com".lower()
        _user(self.user_email, "Resident Supervisor")

        # Grant User Permission only for the allowed building
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

        # Attempt to submit a round for the forbidden building
        # lines list matches the structure submit_round expects
        lines = []

        with self.assertRaises(frappe.PermissionError):
            submit_round(
                building=self.building_forbidden,
                cadence="Daily",
                round_date=today(),
                lines=lines,
            )
