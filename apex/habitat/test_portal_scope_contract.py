from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions
from apex.habitat.api import front_desk


class TestHousingPortalScopeContract(FrappeTestCase):
    def test_resident_supervisor_maintenance_list_uses_building_scope(self):
        with (
            patch.object(permissions, "_resolve_user", return_value="resident@example.com"),
            patch.object(permissions.frappe, "get_roles", return_value=["Resident Supervisor"]),
            patch.object(permissions, "_allowed_buildings_for", return_value=["BLD-1"]),
        ):
            query = permissions.maintenance_request_query(
                user="resident@example.com", doctype="Maintenance Request"
            )

        self.assertIn("`building`", query)
        self.assertIn("BLD-1", query)

    def test_resident_supervisor_cannot_open_other_building_maintenance(self):
        doc = SimpleNamespace(
            doctype="Maintenance Request",
            building="BLD-2",
            owner="resident@example.com",
            assigned_to=None,
        )
        with (
            patch.object(permissions, "_resolve_user", return_value="resident@example.com"),
            patch.object(permissions.frappe, "get_roles", return_value=["Resident Supervisor"]),
            patch.object(permissions, "_allowed_buildings_for", return_value=["BLD-1"]),
        ):
            allowed = permissions.maintenance_request_has_permission(
                doc, "read", user="resident@example.com"
            )

        self.assertFalse(allowed)

    def test_quick_checkout_checks_temporary_worker_party_custody(self):
        assignment = SimpleNamespace(
            name="HAS-1", employee=None, party_type="Temporary Worker", party="TW-1"
        )
        with (
            patch.object(front_desk.frappe, "has_permission"),
            patch.object(front_desk.frappe.db, "get_value", return_value=assignment),
            patch(
                "apex.habitat.doctype.housing_checkout.housing_checkout._outstanding_custody_for_party",
                return_value={"CUST-1": 1},
            ) as outstanding,
        ):
            result = front_desk.quick_check_out("BED-1")

        outstanding.assert_called_once_with("Temporary Worker", "TW-1", None)
        self.assertEqual(result, {"requires_full_form": True, "assignment": "HAS-1"})
