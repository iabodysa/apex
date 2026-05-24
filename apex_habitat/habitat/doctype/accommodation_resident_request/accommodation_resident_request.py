from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class AccommodationResidentRequest(Document):
    def before_insert(self):
        if self.get("website_field"):
            frappe.throw("Invalid submission.", frappe.PermissionError)

        if not self.anonymous_tracking_code:
            self.anonymous_tracking_code = frappe.generate_hash(length=8).upper()

        if not self.source_channel:
            self.source_channel = "QR Web Form"

        if not self.status:
            self.status = "New"

        self.populate_location_from_token()
        self.apply_priority_rules()

    def validate(self):
        if self.location_token and not self.building:
            frappe.throw(_("Invalid or inactive location token."))

        self._validate_status_transition()

    def _validate_status_transition(self):
        """Enforce role-based state transition rules without a full Frappe Workflow."""
        status = self.status or "New"

        if status == "Assigned" and not self.assigned_to:
            frappe.throw(_("Assigned To is required when status is Assigned."))

        if status in ("Resolved", "Closed") and not self.resolution_notes:
            frappe.throw(_("Resolution Notes are required when closing or resolving a request."))

        if status == "Closed" and not self.closed_on:
            self.closed_on = frappe.utils.today()

        if status == "Closed" and not self.closed_by:
            self.closed_by = frappe.session.user

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
