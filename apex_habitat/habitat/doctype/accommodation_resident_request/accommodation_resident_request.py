from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AccommodationResidentRequest(Document):
    def before_insert(self):
        if not self.anonymous_tracking_code:
            self.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

        self.populate_location_from_token()
        self.apply_priority_rules()

    def validate(self):
        if self.location_token and not self.building:
            frappe.throw(_("Invalid or inactive location token."))

    def populate_location_from_token(self):
        if not self.location_token:
            return

        qr = frappe.get_all(
            "Accommodation QR Location",
            filters={"location_token": self.location_token, "is_active": 1},
            fields=["accommodation_site", "building", "room"],
            limit=1,
        )
        if not qr:
            return

        self.accommodation_site = qr[0].accommodation_site
        self.building = qr[0].building
        self.room = qr[0].room

    def apply_priority_rules(self):
        text = f"{self.request_category or ''} {self.description or ''}".lower()

        critical_terms = (
            "fire",
            "electrical hazard",
            "structural",
            "contamination",
            "no drinking water",
            "severe pest",
            "injury",
        )
        high_terms = (
            "ac",
            "air conditioning",
            "bathroom leak",
            "broken bed",
            "missing locker",
            "security",
        )

        if any(term in text for term in critical_terms):
            self.priority = "Critical"
        elif any(term in text for term in high_terms) and self.priority in (None, "", "Low", "Medium"):
            self.priority = "High"
