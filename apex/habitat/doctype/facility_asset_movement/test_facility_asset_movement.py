# Copyright (c) 2026, afmcoltd

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.facility_asset_movement import facility_asset_movement


class TestFacilityAssetMovementAcknowledgement(FrappeTestCase):
    def test_acknowledgement_uses_document_and_field_permissions(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = True

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "get_roles",
                return_value=["Finance Manager"],
            ),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.check_permission.assert_called_once_with("read")
        movement.has_permlevel_access_to.assert_called_once_with(
            "accounting_acknowledged",
            permission_type="write",
        )

    def test_acknowledgement_rejects_field_without_write_permission(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = False

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.db_set.assert_not_called()
