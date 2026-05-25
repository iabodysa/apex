"""Passenger Manifest controller."""

from __future__ import annotations

from frappe.model.document import Document


class PassengerManifest(Document):
    def validate(self):
        self.passenger_count = len(self.passengers or [])
