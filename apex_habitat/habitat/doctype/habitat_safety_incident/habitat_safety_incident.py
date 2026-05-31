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


class HabitatSafetyIncident(Document):
    def validate(self):
        if not self.reported_by:
            self.reported_by = frappe.session.user

        if self.casualties is not None and self.casualties < 0:
            frappe.throw(_("Casualties cannot be negative."))

        if self.status == "Closed" and not (self.resolution_notes or "").strip():
            frappe.throw(_("Resolution Notes are required to close a Habitat Safety Incident."))
