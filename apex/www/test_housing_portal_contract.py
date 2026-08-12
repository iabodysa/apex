from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.www import housing


class TestHousingPortalContract(FrappeTestCase):
    def _capabilities(self, permissions, roles):
        def allowed(doctype, *ptypes):
            return all((doctype, ptype) in permissions for ptype in ptypes)

        with (
            patch.object(housing, "_can", side_effect=allowed),
            patch.object(housing.frappe, "get_roles", return_value=roles),
        ):
            return housing.portal_capabilities()

    def test_manager_contract_includes_operations_but_not_technician_actions(self):
        permissions = {
            ("Building", "read"),
            ("Room", "write"),
            ("Housing Inventory", "read"),
            ("Housing Inventory", "write"),
            ("Housing Assignment", "create"),
            ("Housing Assignment", "submit"),
            ("Housing Checkout", "create"),
            ("Housing Checkout", "submit"),
            ("Room Bed Transfer", "create"),
            ("Room Bed Transfer", "submit"),
            ("Custody Issue", "read"),
            ("Custody Issue", "create"),
            ("Custody Issue", "submit"),
            ("Custody Return", "create"),
            ("Custody Return", "submit"),
            ("Facility Asset Delivery", "read"),
            ("Facility Asset Delivery", "write"),
            ("Maintenance Request", "read"),
            ("Maintenance Request", "create"),
            ("Safety Task Execution", "create"),
            ("Safety Task Execution", "submit"),
        }

        capabilities = self._capabilities(permissions, ["Accommodation Manager"])

        self.assertTrue(capabilities["estate_read"])
        self.assertTrue(capabilities["set_readiness"])
        self.assertTrue(capabilities["maintenance_create"])
        self.assertTrue(capabilities["today"])
        self.assertTrue(capabilities["safety_read"])
        self.assertFalse(capabilities["maintenance_work_order_action"])
        self.assertEqual(housing.portal_landing(capabilities), "/overview")

    def test_procurement_only_lands_on_delivery(self):
        permissions = {
            ("Facility Asset Delivery", "read"),
            ("Facility Asset Delivery", "write"),
        }
        capabilities = self._capabilities(permissions, ["Procurement Supervisor"])

        self.assertFalse(capabilities["estate_read"])
        self.assertEqual(capabilities["exits"], [1])
        self.assertTrue(capabilities["clear_exit_1"])
        self.assertFalse(capabilities["clear_exit_3"])
        self.assertEqual(housing.portal_landing(capabilities), "/delivery")

    def test_safety_only_lands_on_safety_rounds(self):
        permissions = {
            ("Building", "read"),
            ("Safety Task Execution", "create"),
        }
        capabilities = self._capabilities(permissions, ["Safety Officer"])

        self.assertTrue(capabilities["safety_draft"])
        self.assertTrue(capabilities["safety_read"])
        self.assertFalse(capabilities["safety_check"])
        self.assertEqual(housing.portal_landing(capabilities), "/rounds")

    def test_resident_supervisor_lands_on_today_and_cannot_submit_custody(self):
        permissions = {
            ("Building", "read"),
            ("Housing Assignment", "create"),
            ("Housing Assignment", "submit"),
            ("Housing Checkout", "create"),
            ("Housing Checkout", "submit"),
            ("Custody Issue", "read"),
            ("Maintenance Request", "read"),
            ("Maintenance Request", "create"),
            ("Safety Task Execution", "create"),
            ("Safety Task Execution", "submit"),
        }
        capabilities = self._capabilities(permissions, ["Resident Supervisor"])

        self.assertTrue(capabilities["custody_read"])
        self.assertFalse(capabilities["issue_custody"])
        self.assertEqual(housing.portal_landing(capabilities), "/today")
