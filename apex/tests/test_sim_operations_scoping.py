# Copyright (c) 2026, AFMCO and contributors
"""Company row-scoping tests for SIM Operations.

A SIM Operations User acts only on records in the companies it holds a User
Permission for; an oversight role (Finance Manager) sees every company. The same
rules apply to the has_permission hook (direct/form access) and the
permission_query_conditions fragment (list/report), and no business role may
delete a SIM Operations record.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.logistay import permissions
from apex.tests import factories
from apex.tests._helpers import _user


class TestSIMOperationsScoping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company_a = factories.make_company("Test AFMCO").name
        cls.company_b = factories.make_company("Other AFMCO", abbr="OAFM").name
        cls.scoped = _user("sim_scope@example.com", "SIM Operations User")
        cls.no_perm = _user("sim_noperm@example.com", "SIM Operations User")
        cls.oversight = _user("sim_finance@example.com", "Finance Manager")
        if not frappe.db.exists(
            "User Permission", {"allow": "Company", "for_value": cls.company_a, "user": cls.scoped}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Company",
                    "for_value": cls.company_a,
                    "user": cls.scoped,
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission", {"allow": "Company", "for_value": cls.company_a, "user": cls.scoped}
        )
        frappe.db.commit()
        super().tearDownClass()

    def _doc(self, company):
        return frappe._dict({"doctype": "SIM Card", "company": company})

    # has_permission

    def test_scoped_user_allowed_in_company(self):
        self.assertIsNone(
            permissions.company_scoped_has_permission(self._doc(self.company_a), "read", user=self.scoped)
        )

    def test_scoped_user_denied_other_company(self):
        self.assertFalse(
            permissions.company_scoped_has_permission(self._doc(self.company_b), "read", user=self.scoped)
        )

    def test_scoped_user_denied_null_company(self):
        self.assertFalse(
            permissions.company_scoped_has_permission(self._doc(None), "read", user=self.scoped)
        )

    def test_oversight_sees_everything(self):
        self.assertIsNone(
            permissions.company_scoped_has_permission(self._doc(self.company_b), "read", user=self.oversight)
        )

    # permission_query_conditions

    def test_query_fragment_scopes_to_company(self):
        fragment = permissions.telecom_contract_query(self.scoped)
        self.assertIn("company", fragment)
        self.assertIn(self.company_a, fragment)

    def test_query_fragment_empty_for_oversight(self):
        self.assertEqual(permissions.sim_card_query(self.oversight), "")

    def test_query_fragment_blocks_scoped_user_without_permission(self):
        self.assertEqual(permissions.sim_custody_assignment_query(self.no_perm), "1=0")

    # Deletion authority

    def test_no_delete_for_sim_operations_user(self):
        for dt in ("Telecom Contract", "SIM Card", "SIM Custody Assignment"):
            perms = frappe.get_meta(dt).permissions
            business = [p for p in perms if p.role == "SIM Operations User"]
            self.assertTrue(business, f"{dt} must grant SIM Operations User")
            self.assertFalse(any(p.delete for p in business), f"{dt} must not let SIM Operations User delete")
            system = [p for p in perms if p.role == "System Manager"]
            self.assertTrue(any(p.delete for p in system), f"{dt} must let System Manager delete")
