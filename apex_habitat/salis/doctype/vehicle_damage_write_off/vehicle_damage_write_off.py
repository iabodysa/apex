"""Vehicle Damage Write-Off controller.

Submittable damage write-off case raised from a Vehicle Handover discrepancy.
Enforces a SAR-tiered write-off authority gate on submit:
high-value cases (>= 2000 SAR) require Operations-tier approval; lower-value
cases require at least Regional-tier approval.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note, ensure_approval

# Fallback estimated cost (SAR) at or above which Operations-tier authority is
# required, used only when Salis Settings has no configured threshold.
_OPERATIONS_TIER_THRESHOLD_DEFAULT = 2000


class VehicleDamageWriteOff(Document):
    def validate(self):
        # Evidence is mandatory before the case can advance beyond Open.
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        self._stamp_approver()

    def before_submit(self):
        # Threshold is configurable via Salis Settings so the SAR write-off gate
        # can be tuned without a code change; fall back to the default if unset.
        threshold = frappe.db.get_single_value(
            "Salis Settings", "writeoff_ops_threshold_sar"
        )
        if not threshold:
            threshold = _OPERATIONS_TIER_THRESHOLD_DEFAULT
        required_tier = "Operations" if (self.estimated_cost or 0) >= threshold else "Regional"
        ensure_approval("Vehicle Damage Write-Off", self.name, required_tier=required_tier)

    def on_submit(self):
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} submitted (estimated {1} SAR).").format(
                self.name, self.estimated_cost
            ),
        )

    def on_cancel(self):
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} cancelled.").format(self.name),
        )

    # ------------------------------------------------------------------ helpers

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user
