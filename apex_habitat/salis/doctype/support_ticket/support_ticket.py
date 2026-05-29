"""Support Ticket controller.

Status transitions are owned by the native **Support Ticket Workflow** (see
``salis/workflow/support_ticket_workflow/``), not by this controller. The desk
progression (New -> In Progress -> Waiting -> Resolved -> Closed, with Reopen
and a Cancel off Closed) is staff-only: a Driver may open a ticket and read
their own (the ``if_owner`` Driver DocPerm), but the resolve/close transitions
are restricted to staff roles by the workflow. This controller keeps the
*data* guards: it rejects an unknown status value, keeps the initial-state guard
(a new ticket may only be created at New — closes the insert-bypass the workflow
does not cover), and stamps message rows. The "Close" transition submits the
document (docstatus 0 -> 1); "Cancel" off Closed cancels it (1 -> 2)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Known status values. The Select carries these for filtering/colour, but the
# Support Ticket Workflow owns the *transitions*.
VALID_STATUSES = ("New", "In Progress", "Waiting", "Resolved", "Closed", "Cancelled")


class SupportTicket(Document):
    def validate(self):
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        self._guard_initial_status()
        self._stamp_messages()

    def _guard_initial_status(self):
        """A new ticket may only be created as New — closes the insert-bypass
        where a doc is inserted directly at a later/terminal status. Transitions
        between states are owned by the Support Ticket Workflow."""
        before = self.get_doc_before_save()
        if before and before.status:
            return
        if self.status and self.status != "New":
            frappe.throw(
                _("A new Support Ticket must start as New, not {0}.").format(_(self.status))
            )

    def _stamp_messages(self):
        # Append-only stamping: only fill blanks, never overwrite history.
        for row in self.messages or []:
            if not row.sender:
                row.sender = frappe.session.user
            if not row.sent_at:
                row.sent_at = now_datetime()

    # Submit is recorded natively (Version track_changes + auto-comment).
