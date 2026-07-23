# Copyright (c) 2026, AFMCO and contributors
"""Salis Vehicle controller."""

from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

from apex.salis.utils import normalize_plate

DEFAULT_ALERT_LEAD_DAYS = 30

_STATUS_RANK = {"Compliant": 0, "Expiring Soon": 1, "Expired": 2}


class SalisVehicle(Document):
    # [#cuw3j6]
    def validate(self):
        self._set_company_default()
        self._set_plate_normalized()
        self._set_compliance_status()

    def _set_company_default(self):
        """Default the owning company from Salis Settings (asset ownership /
        reporting context). Reference field only - no GL is posted."""
        if not self.company:
            from apex.apex_core.doctype.salis_settings.salis_settings import (
                get_default_company,
            )

            self.company = get_default_company()

    def _set_plate_normalized(self):
        if self.plate_number:
            self.plate_normalized = normalize_plate(self.plate_number)
        else:
            self.plate_normalized = None

    def _set_compliance_status(self):
        rows = self.get("compliance_documents") or []
        if not rows:
            self.compliance_status = "Not Tracked"
            self.next_expiry_date = None
            return

        today_date = getdate(today())
        lead_days = self._get_alert_lead_days()
        soon_cutoff = add_days(today_date, lead_days)

        # [#isa0o3]
        row_to_parent = {
            "Expired": "Expired",
            "Expiring Soon": "Expiring Soon",
            "Valid": "Compliant",
        }

        worst_rank = -1
        worst_status = "Compliant"
        future_expiries = []
        all_expiries = []

        for row in rows:
            if not row.expiry_date:
                continue
            expiry = getdate(row.expiry_date)
            all_expiries.append(expiry)
            if expiry >= today_date:
                future_expiries.append(expiry)

            if expiry < today_date:
                row.status = "Expired"
            elif expiry <= soon_cutoff:
                row.status = "Expiring Soon"
            else:
                row.status = "Valid"

            parent_status = row_to_parent[row.status]
            rank = _STATUS_RANK[parent_status]
            if rank > worst_rank:
                worst_rank = rank
                worst_status = parent_status

        if worst_rank < 0:
            # [#6wml3f]
            self.compliance_status = "Not Tracked"
            self.next_expiry_date = None
            return

        self.compliance_status = worst_status

        if future_expiries:
            self.next_expiry_date = min(future_expiries)
        elif all_expiries:
            self.next_expiry_date = min(all_expiries)
        else:
            self.next_expiry_date = None

    @staticmethod
    def _get_alert_lead_days():
        # [#nt5cx7]
        from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

        return get_salis_int("alert_lead_days", DEFAULT_ALERT_LEAD_DAYS)
