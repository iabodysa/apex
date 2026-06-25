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

from apex_habitat.salis.utils import add_timeline_note


class VehicleDamageWriteOff(Document):
    def validate(self):
        # [#83ntz1]
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        self._stamp_approver()

    def on_submit(self):
        self._stamp_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} submitted (estimated {1} SAR).").format(
                self.name, self.estimated_cost
            ),
        )

    def on_cancel(self):
        self._clear_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} cancelled.").format(self.name),
        )

    # [#f9hua6]

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user

    def _stamp_source_incident(self):
        # Complete the escalation back-link: the incident's read_only write_off_case
        # is only ever populated here, making the Incident<->Write-Off link bidirectional.
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", self.name
            )

    def _clear_source_incident(self):
        # Reverse the back-link on cancel so no stale write_off_case pointer survives.
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", None
            )
