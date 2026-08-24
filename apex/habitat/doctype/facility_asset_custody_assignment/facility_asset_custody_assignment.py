# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class FacilityAssetCustodyAssignment(Document):
    def before_submit(self):
        if not self.get("assets_in_custody"):
            frappe.throw(_("Asset table cannot be empty."))
        if not self.all_assets_verified:
            frappe.throw(_("All Assets Physically Verified must be checked before submitting the custody assignment."))

    def on_submit(self):
        for row in self.assets_in_custody:
            if not row.facility_asset:
                continue
            frappe.db.set_value(
                "Facility Asset", row.facility_asset, "responsible_supervisor", self.supervisor
            )

    def on_cancel(self):
        for row in self.assets_in_custody:
            if not row.facility_asset:
                continue
            current = frappe.db.get_value(
                "Facility Asset", row.facility_asset, "responsible_supervisor"
            )
            if current != self.supervisor:
                continue
            prior = self._prior_custodian(row.facility_asset)
            if prior:
                frappe.db.set_value(
                    "Facility Asset", row.facility_asset, "responsible_supervisor", prior
                )

    def _prior_custodian(self, facility_asset):
        rows = frappe.get_all(
            "Facility Custody Item",
            filters={
                "facility_asset": facility_asset,
                "parenttype": "Facility Asset Custody Assignment",
                "parent": ["!=", self.name],
            },
            fields=["parent"],
        )
        parents = [r.parent for r in rows]
        if not parents:
            return None
        prior = frappe.get_all(
            "Facility Asset Custody Assignment",
            filters={"name": ["in", parents], "docstatus": 1},
            fields=["supervisor"],
            order_by="handover_date desc, modified desc",
            limit=1,
        )
        return prior[0].supervisor if prior else None
