# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SafetyIncident(Document):
    def validate(self):
        if not self.reported_by:
            self.reported_by = frappe.session.user

        if self.status == "Closed" and not (self.resolution_notes or "").strip():
            frappe.throw(_("Resolution Notes are required to close a Safety Incident."))

        self._stamp_closure()

    def _stamp_closure(self):
        if self.status == "Closed":
            if not self.closed_on:
                self.closed_on = frappe.utils.nowdate()
                self.closed_by = frappe.session.user
        else:
            self.closed_on = None
            self.closed_by = None
