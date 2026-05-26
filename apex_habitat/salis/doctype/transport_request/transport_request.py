"""Transport Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

VALID_STATUSES = ("New", "Approved", "Scheduled", "Completed", "Rejected", "Cancelled")


class TransportRequest(Document):
    def before_insert(self):
        # Honeypot guard for any controller-level path.
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

        # Web / anonymous (guest) submissions: tag the channel and mint a tracking code.
        if not self.requested_by or frappe.session.user == "Guest":
            self.source_channel = "Web QR"

        if not self.source_channel:
            self.source_channel = "Desk"

        if self.source_channel == "Web QR" and not self.anonymous_tracking_code:
            self.anonymous_tracking_code = "TRQ" + frappe.generate_hash(length=8).upper()

        if not self.status:
            self.status = "New"

    def validate(self):
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        if self.passenger_count:
            count = int(self.passenger_count)
            if count < 1:
                count = 1
            elif count > 50:
                count = 50
            self.passenger_count = count

        if self.purpose and len(self.purpose) > 2000:
            frappe.throw(_("Purpose is too long. Please keep it under 2000 characters."))
