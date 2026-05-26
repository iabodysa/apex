"""Sponsorship Transfer Case controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import ensure_approval, log_activity

# Allowed forward status transitions. Cancellation is allowed from any state.
_ALLOWED_TRANSITIONS = {
    "Open": {"Open", "In Progress", "Cancelled"},
    "In Progress": {"In Progress", "Completed", "Cancelled"},
    "Completed": {"Completed", "Cancelled"},
    "Cancelled": {"Cancelled"},
}


class SponsorshipTransferCase(Document):
    def validate(self):
        self._enforce_status_flow()
        self._gate_completion()

    def _enforce_status_flow(self):
        before = self.get_doc_before_save()
        if not before or not before.status:
            return
        old, new = before.status, self.status
        if new == old:
            return
        if new not in _ALLOWED_TRANSITIONS.get(old, set()):
            frappe.throw(
                _("Illegal status change from {0} to {1}.").format(_(old), _(new))
            )

    def _gate_completion(self):
        if self.status == "Completed":
            if self.qiwa_status != "Approved" or not self.clearance_done:
                frappe.throw(
                    _("Cannot complete: Qiwa must be Approved and clearance done.")
                )

    def before_submit(self):
        # Sponsorship transfers are high-risk legal/government actions and must
        # carry Operations-tier authority (tiered authorityG08).
        ensure_approval(
            "Sponsorship Transfer Case", self.name, required_tier="Operations"
        )

    def on_submit(self):
        log_activity(
            action="Sponsorship Transfer Completed",
            entity_type="Employee",
            entity_name=self.employee,
            details={"case": self.name, "status": self.status},
        )

    def on_cancel(self):
        log_activity(
            action="Sponsorship Transfer Cancelled",
            entity_type="Employee",
            entity_name=self.employee,
            details={"case": self.name},
        )
