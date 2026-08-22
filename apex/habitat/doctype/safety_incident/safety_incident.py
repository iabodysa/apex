# Copyright (c) 2026, afmcoltd
"""Habitat Safety Incident controller.

Formal accommodation/housing safety-incident record. Management escalation for
Severe/Critical incidents is handled natively by the seeded Frappe Notification
"Habitat - Severe Safety Incident" (seeded by ``habitat/notifications_seed.py`` via
setup.after_install and the v1_x seed patch), not by hard-coded email here.

Validation is implemented as class-based ``validate`` so the controller needs no
``hooks.py`` doc_events registration (Frappe invokes class hooks automatically).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SafetyIncident(Document):
    def validate(self):
        """Defaults reported_by and requires notes to close the incident."""
        if not self.reported_by:
            self.reported_by = frappe.session.user

        if self.status == "Closed" and not (self.resolution_notes or "").strip():
            frappe.throw(_("Resolution Notes are required to close a Safety Incident."))

        self._stamp_closure()

    def _stamp_closure(self):
        """Record who closed the incident and when, so time-to-close is on the record.

        An auditor reads the printed report, not the version history, and a status of
        Closed with no date cannot answer how long the site carried the hazard. Both
        fields are read-only and set here; reopening clears them so a reopened incident
        never prints a closure it no longer has.
        """
        if self.status == "Closed":
            if not self.closed_on:
                self.closed_on = frappe.utils.nowdate()
                self.closed_by = frappe.session.user
        else:
            self.closed_on = None
            self.closed_by = None
