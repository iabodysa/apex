# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestAccountingAcknowledgedIsSubmitLocked(FrappeTestCase):
    def _submitted_movement(self):
        asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": "_T-Movement-Submit-Lock-Asset",
                "asset_category": "Other",
                "building": "_Test Building",
                "responsible_supervisor": "Administrator",
            }
        ).insert()
        movement = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": asset.name,
                "movement_category": "Same-Company Relocation",
                "to_building": "_Test Building 2",
            }
        ).insert()
        movement.submit()
        return movement

    def test_accounting_acknowledged_can_no_longer_be_saved_after_submit(self):
        movement = self._submitted_movement()
        movement.accounting_acknowledged = 1
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            movement.save()

    def test_accounting_acknowledged_by_can_no_longer_be_saved_after_submit(self):
        movement = self._submitted_movement()
        movement.accounting_acknowledged_by = "Administrator"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            movement.save()
