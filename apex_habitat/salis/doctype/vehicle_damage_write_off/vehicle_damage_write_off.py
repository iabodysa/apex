"""Vehicle Damage Write-Off controller.

Submittable damage write-off case raised from a Vehicle Handover discrepancy.
Enforces a SAR-tiered write-off authority gate on submit (tiered authority):
high-value cases (>= 2000 SAR) require Operations-tier approval; lower-value
cases require at least Regional-tier approval.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval, log_activity

# Estimated cost (SAR) at or above which Operations-tier authority is required.
_OPERATIONS_TIER_THRESHOLD = 2000


class VehicleDamageWriteOff(Document):
    def validate(self):
        # Evidence is mandatory before the case can advance beyond Open.
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        self._stamp_approver()

    def before_submit(self):
        required_tier = "Operations" if (self.estimated_cost or 0) >= _OPERATIONS_TIER_THRESHOLD else "Regional"
        ensure_approval("Vehicle Damage Write-Off", self.name, required_tier=required_tier)

    def on_submit(self):
        log_activity(
            action="Vehicle Damage Write-Off Submitted",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={
                "writeoff": self.name,
                "source_handover": self.source_handover,
                "driver": self.driver,
                "estimated_cost": self.estimated_cost,
                "recommended_action": self.recommended_action,
            },
        )

    def on_cancel(self):
        log_activity(
            action="Vehicle Damage Write-Off Cancelled",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={"writeoff": self.name},
        )

    # ------------------------------------------------------------------ helpers

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user
