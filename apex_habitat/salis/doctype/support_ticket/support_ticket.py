"""Support Ticket controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Allowed status transitions. Closed is terminal except via amend.
_ALLOWED_TRANSITIONS = {
    "New": {"New", "In Progress"},
    "In Progress": {"In Progress", "Waiting", "Resolved"},
    "Waiting": {"Waiting", "In Progress", "Resolved"},
    "Resolved": {"Resolved", "In Progress", "Closed"},
    "Closed": {"Closed"},
}


class SupportTicket(Document):
    def validate(self):
        self._enforce_status_flow()
        self._stamp_messages()

    def _enforce_status_flow(self):
        before = self.get_doc_before_save()
        if not before or not before.status:
            # A new ticket may only be created as New — closes the insert-bypass
            # where a doc is inserted directly at a later/terminal status.
            if self.status and self.status != "New":
                frappe.throw(
                    _("A new Support Ticket must start as New, not {0}.").format(_(self.status))
                )
            return
        old, new = before.status, self.status
        if new == old:
            return
        if new not in _ALLOWED_TRANSITIONS.get(old, set()):
            frappe.throw(
                _("Illegal status change from {0} to {1}.").format(_(old), _(new))
            )

    def _stamp_messages(self):
        # Append-only stamping: only fill blanks, never overwrite history.
        for row in self.messages or []:
            if not row.sender:
                row.sender = frappe.session.user
            if not row.sent_at:
                row.sent_at = now_datetime()

    # Submit is recorded natively (Version track_changes + auto-comment).
