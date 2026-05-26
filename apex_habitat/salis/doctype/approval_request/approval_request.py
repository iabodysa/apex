"""Approval Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from apex_habitat.salis.salis_lib import log_activity


class ApprovalRequest(Document):
    def validate(self):
        self._enforce_segregation_of_duties()
        self._stamp_decision_date()

    def _enforce_segregation_of_duties(self):
        # Core control: the approver must never be the requester.
        if self.approver and self.requested_by and self.approver == self.requested_by:
            frappe.throw(_("Approver must be different from the requester."))

    def _stamp_decision_date(self):
        if self.decision in ("Approved", "Rejected"):
            if not self.decision_date:
                self.decision_date = now_datetime()
        elif self.decision == "Pending":
            self.decision_date = None

    def before_submit(self):
        if self.decision == "Pending":
            frappe.throw(
                _("A decision (Approved or Rejected) is required before submitting.")
            )

    def on_submit(self):
        log_activity(
            action="Approval {0}".format(self.decision),
            entity_type=self.reference_doctype or "Approval",
            entity_name=self.reference_name or self.name,
            details={"request_type": self.request_type, "remarks": self.remarks},
        )
