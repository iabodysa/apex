"""Sponsorship Transfer Case controller.

Status transitions are owned by the native **Sponsorship Transfer Case
Workflow** (see ``salis/workflow/sponsorship_transfer_case_workflow/``), not by
this controller. The internal flow (Open -> In Progress -> Completed, with a
Cancel off Completed) carries the high-risk legal/government control on its
submitting transition: "Complete" (In Progress -> Completed, docstatus 0 -> 1)
is restricted to the **Fleet Manager** (Operations tier) and gated by the
workflow ``condition`` ``qiwa_status == 'Approved' and clearance_done``,
mirroring the completion guard below. ``_gate_completion`` stays as the hard
server-side block (defence in depth: it fires on any save that lands the case in
Completed, including a path that bypasses the workflow action)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import add_timeline_note

# Known status values. The Select carries these for filtering/colour, but the
# Sponsorship Transfer Case Workflow owns the *transitions*.
VALID_STATUSES = ("Open", "In Progress", "Completed", "Cancelled")


class SponsorshipTransferCase(Document):
    def validate(self):
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        self._gate_completion()

    def _gate_completion(self):
        if self.status == "Completed":
            if self.qiwa_status != "Approved" or not self.clearance_done:
                frappe.throw(
                    _("Cannot complete: Qiwa must be Approved and clearance done.")
                )

    def on_submit(self):
        # The case's own submit is captured natively; annotate the Employee.
        add_timeline_note(
            "Employee",
            self.employee,
            _("Sponsorship Transfer Case {0} submitted (status {1}).").format(
                self.name, _(self.status)
            ),
        )

    def on_cancel(self):
        add_timeline_note(
            "Employee",
            self.employee,
            _("Sponsorship Transfer Case {0} cancelled.").format(self.name),
        )
