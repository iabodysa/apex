# Copyright (c) 2026, afmcoltd
"""``accounting_acknowledged`` and ``accounting_acknowledged_by`` are ONLY ever
written by ``acknowledge_intercompany_movement``'s ``doc.db_set(...)`` (which
runs no controller validation and so needs no ``allow_on_submit``); grep across
``apex/`` and ``frontend/`` turns up no other writer. Both were left
``allow_on_submit: 1`` regardless, opening a plain ``save()`` edit path the app
never used. Removing the flag closes it; this proves the framework itself
(``_validate_update_after_submit``, frappe/model/base_document.py) now refuses
the edit.
"""

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
