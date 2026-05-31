"""Vehicle Damage Write-Off controller.

Submittable damage write-off case raised from a Vehicle Handover discrepancy.
Write-off authority is enforced by the native Frappe Workflow "Vehicle Damage
Write-Off Workflow": the Approve transition is restricted to the Fleet Manager /
System Manager roles, with self-approval disabled.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note


class VehicleDamageWriteOff(Document):
    def validate(self):
        # Evidence is mandatory before the case can advance beyond Open.
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        self._stamp_approver()

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
