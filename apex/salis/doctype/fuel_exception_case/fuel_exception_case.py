# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

VALID_STATUSES = (
    "Open",
    "Under Investigation",
    "Evidence Required",
    "Resolved",
    "Rejected",
    "Closed",
)

_CLOSING_STATUSES = {"Resolved", "Closed"}


class FuelExceptionCase(Document):
    def validate(self):
        if not self.reported_by:
            self.reported_by = frappe.session.user
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        self._guard_initial_status()
        self._enforce_closure_controls()

    def _guard_initial_status(self):
        if self.is_new() and self.status and self.status != "Open":
            frappe.throw(
                _("A Fuel Exception Case must be created with status Open; {0} is reached through the workflow.").format(
                    _(self.status)
                )
            )

    def _enforce_closure_controls(self):
        if self.status not in _CLOSING_STATUSES:
            return

        if not (self.evidence or self.evidence_notes):
            frappe.throw(_("Evidence required before resolving"))

        self.closed_by = frappe.session.user
        if self.closed_by == self.reported_by:
            frappe.throw(_("The closer must differ from the person who raised the case."))
