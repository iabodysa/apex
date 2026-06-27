"""Facility Asset Custody Assignment controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FacilityAssetCustodyAssignment(Document):
    def before_submit(self):
        # Custody cannot transfer until the assets are physically verified.
        if not self.all_assets_verified:
            frappe.throw(_("All Assets Physically Verified must be checked before submitting the custody assignment."))
