"""Approval Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from apex_habitat.salis.salis_lib import (
    add_timeline_note,
    escalation_target,
    user_max_tier,
)


class ApprovalRequest(Document):
    def validate(self):
        self._enforce_segregation_of_duties()
        self._stamp_decision_date()
        self._evaluate_escalation()

    def _evaluate_escalation(self):
        # When the approver lacks the required tier, route and
        # record the escalation instead of relying solely on the submit-time
        # throw in ensure_approval.
        if not self.required_tier:
            self.escalation_state = None
            self.escalated_to_tier = None
            return

        target = escalation_target(self.required_tier, self.approver)
        if not target:
            # Approver holds at least the required tier.
            self.escalation_state = "Within Authority"
            self.escalated_to_tier = None
            return

        self.escalation_state = "Escalated"
        self.escalated_to_tier = target
        self._append_escalation_log(target)

    def _append_escalation_log(self, target):
        approver_tier = user_max_tier(self.approver) or _("none")
        line = _(
            "{0} — Escalated to {1} tier: approver {2} holds {3}, request requires {4}."
        ).format(
            now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
            target,
            self.approver or _("unassigned"),
            approver_tier,
            self.required_tier,
        )
        existing = (self.escalation_log or "").rstrip()
        # Avoid duplicating an identical trailing entry on repeated saves.
        if existing.endswith(line):
            return
        self.escalation_log = (existing + "\n" + line).strip() if existing else line

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
        # Annotate the referenced source document's timeline with the decision.
        # The Approval Request's own submit is captured natively by Version.
        if self.reference_doctype and self.reference_name:
            add_timeline_note(
                self.reference_doctype,
                self.reference_name,
                _("Approval Request {0}: {1}.").format(self.name, _(self.decision)),
            )
