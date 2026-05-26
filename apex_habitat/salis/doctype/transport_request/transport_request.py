"""Transport Request controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

VALID_STATUSES = (
    "New",
    "Validated",
    "Approved",
    "Scheduled",
    "Fulfilled",
    "Rejected",
    "Cancelled",
)

# Allowed request types per service line (two-division model).
SERVICE_LINE_REQUEST_TYPES = {
    "Workers": (
        "Accommodation to Project Shuttle",
        "Inter-City Relocation",
    ),
    "Representatives": (
        "Administrative Trip / Document Signing",
    ),
}


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

        # Enforce the service_line -> request_type pairing (two-division model).
        if self.service_line and self.request_type:
            allowed = SERVICE_LINE_REQUEST_TYPES.get(self.service_line, ())
            if self.request_type not in allowed:
                frappe.throw(
                    _("Request Type {0} is not valid for the {1} service line.").format(
                        self.request_type, self.service_line
                    )
                )

        # Worker count is always derived from the child rows.
        self.worker_count = len(self.workers or [])

        if self.request_type == "Accommodation to Project Shuttle":
            if not self.accommodation_building or not self.project:
                frappe.throw(
                    _("Accommodation Building and Project are required for an Accommodation to Project Shuttle.")
                )
        elif self.request_type == "Inter-City Relocation":
            if not (self.workers or []):
                frappe.throw(_("At least one worker is required for an Inter-City Relocation."))
        elif self.request_type == "Administrative Trip / Document Signing":
            if not self.destination:
                frappe.throw(_("Destination is required for an Administrative Trip / Document Signing."))

        if self.passenger_count:
            count = int(self.passenger_count)
            if count < 1:
                count = 1
            elif count > 50:
                count = 50
            self.passenger_count = count

        if self.purpose and len(self.purpose) > 2000:
            frappe.throw(_("Purpose is too long. Please keep it under 2000 characters."))

    def before_submit(self):
        from apex_habitat.salis.salis_lib import ensure_approval

        worker_count = self.worker_count or 0
        trips = self.trips_this_month or 0

        needs_operations = (
            (self.request_type == "Inter-City Relocation" and worker_count > 20)
            or (self.request_type == "Administrative Trip / Document Signing" and trips > 5)
            or (self.request_type == "Accommodation to Project Shuttle" and self.is_cross_region)
        )
        required_tier = "Operations" if needs_operations else "Regional"

        ensure_approval("Transport Request", self.name, required_tier=required_tier)

    def on_submit(self):
        from apex_habitat.salis.salis_lib import log_activity

        log_activity("submit", "Transport Request", self.name)

    def on_cancel(self):
        from apex_habitat.salis.salis_lib import log_activity

        log_activity("cancel", "Transport Request", self.name)
