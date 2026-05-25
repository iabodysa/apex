"""Route Plan controller."""

from __future__ import annotations

from frappe.model.document import Document


class RoutePlan(Document):
    def validate(self):
        self.total_stops = len(self.stops or [])
