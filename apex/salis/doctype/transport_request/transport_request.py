# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_first_day, get_last_day, getdate, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

VALID_STATUSES = (
    "New",
    "Validated",
    "Approved",
    "Scheduled",
    "Fulfilled",
    "Rejected",
    "Cancelled",
)

WORKER_MANIFEST_SERVICE_LINES = ("Site Transport", "Inter-City Relocation")

SERVICE_LINE_REQUEST_TYPE = {
    "Site Transport": "Accommodation to Project Shuttle",
    "Inter-City Relocation": "Inter-City Relocation",
    "Administrative Trip": "Administrative Trip / Document Signing",
}


class TransportRequest(Document):
    def before_insert(self):
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

        if self.requested_by == "Guest":
            self.requested_by = None

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

        if self.service_line:
            implied = SERVICE_LINE_REQUEST_TYPE.get(self.service_line)
            if implied:
                if not self.request_type:
                    self.request_type = implied
                elif self.request_type != implied:
                    frappe.throw(
                        _("Request Type {0} is not valid for the {1} transport type.").format(
                            self.request_type, self.service_line
                        )
                    )

        if self.service_line and self.service_line not in WORKER_MANIFEST_SERVICE_LINES:
            if self.accommodation_building:
                frappe.throw(_("An Administrative Trip cannot be linked to labour accommodation."))
            if self.workers or []:
                frappe.throw(_("An Administrative Trip cannot carry a worker manifest."))

        self.worker_count = len(self.workers or [])

        self._derive_trips_this_month()

        self._derive_needs_operations()

        if self.request_type == "Accommodation to Project Shuttle":
            if not self.accommodation_building or not self.project:
                frappe.throw(
                    _("Building and Project are required for an Accommodation to Project Shuttle.")
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

    def _derive_trips_this_month(self):
        if self.request_type != "Administrative Trip / Document Signing":
            self.trips_this_month = 0
            return
        ref = getdate(self.pickup_datetime or today())
        start = get_first_day(ref)
        end = add_days(get_last_day(ref), 1)
        filters = [
            ["Transport Request", "request_type", "=", "Administrative Trip / Document Signing"],
            ["Transport Request", "docstatus", "=", 1],
            ["Transport Request", "pickup_datetime", ">=", str(start)],
            ["Transport Request", "pickup_datetime", "<", str(end)],
        ]
        if self.project:
            filters.append(["Transport Request", "project", "=", self.project])
        elif self.requested_by:
            filters.append(["Transport Request", "requested_by", "=", self.requested_by])
        if self.name:
            filters.append(["Transport Request", "name", "!=", self.name])
        existing = frappe.get_all("Transport Request", filters=filters, limit=0)
        self.trips_this_month = len(existing) + 1

    def _derive_needs_operations(self):
        worker_count = self.worker_count or 0
        trips = self.trips_this_month or 0

        ops_threshold = get_salis_int("passenger_count_ops_threshold", 20)
        admin_trip_threshold = get_salis_int("admin_trip_ops_threshold", 5)

        self.needs_operations = 1 if (
            (self.request_type == "Inter-City Relocation" and worker_count > ops_threshold)
            or (self.request_type == "Administrative Trip / Document Signing" and trips > admin_trip_threshold)
            or (self.request_type == "Accommodation to Project Shuttle" and self.is_cross_region)
        ) else 0
