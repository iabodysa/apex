# Copyright (c) 2026, AFMCO and contributors
"""Transport Request controller.

Transitions are owned by the native **Transport Request Workflow** (see
``salis/workflow/transport_request_workflow/``), not by this controller. The
workflow enforces the role per transition, the Segregation-of-Duties gate
(approver != requester) and the Delegation-of-Authority tier escalation via its
transition ``condition``s.

This controller keeps only the *data* guards: the transport-type (``service_line``)
-> request_type consistency, the per-request-type required fields/evidence, and the
**server-side DoA derivation** that sets ``needs_operations`` so the workflow's tier
gate cannot be under-stated by a client. ``worker_count`` and ``trips_this_month``
are likewise derived server-side, never trusted from the form.

``service_line`` is the **transport type** (AFMCO Movement Department
coordination): ``Site Transport`` (gov item 60 — accommodation->site workforce
transport), ``Inter-City Relocation`` (gov item 61 — inter-city workforce
relocation) and ``Administrative Trip`` (gov item 62 — document/administrative
trips). The first two carry a worker manifest; an Administrative Trip is a simple
trip and carries none. Rider-vehicle custody (gov item 63) is NOT a transport
request — it is handled by Vehicle Assignment + Vehicle Handover.
"""

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

# [#bjtprj]
WORKER_MANIFEST_SERVICE_LINES = ("Site Transport", "Inter-City Relocation")

# [#40xju0]
SERVICE_LINE_REQUEST_TYPE = {
    "Site Transport": "Accommodation to Project Shuttle",
    "Inter-City Relocation": "Inter-City Relocation",
    "Administrative Trip": "Administrative Trip / Document Signing",
}


class TransportRequest(Document):
    def before_insert(self):
        # [#2bwiwy]
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

        # The requested_by __user default records "Guest" for anonymous QR
        # submissions; keep the anonymous path requester-less so tracking stays
        # code-based, not tied to the Guest user row.
        if self.requested_by == "Guest":
            self.requested_by = None

        # [#byh3b2]
        if not self.requested_by or frappe.session.user == "Guest":
            self.source_channel = "Web QR"

        if not self.source_channel:
            self.source_channel = "Desk"

        if self.source_channel == "Web QR" and not self.anonymous_tracking_code:
            self.anonymous_tracking_code = "TRQ" + frappe.generate_hash(length=8).upper()

        if not self.status:
            self.status = "New"

    def validate(self):
        # [#3wtym8]
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        # [#pxwfd7]
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

        # [#702k8m]
        if self.service_line and self.service_line not in WORKER_MANIFEST_SERVICE_LINES:
            if self.accommodation_building:
                frappe.throw(_("An Administrative Trip cannot be linked to labour accommodation."))
            if self.workers or []:
                frappe.throw(_("An Administrative Trip cannot carry a worker manifest."))

        # [#pclxko]
        self.worker_count = len(self.workers or [])

        # [#dovve2]
        self._derive_trips_this_month()

        # [#jr7qsi]
        self._derive_needs_operations()

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

    def _derive_trips_this_month(self):
        """Count submitted Administrative Trips this month for the same project (or
        requester), including this one — server-derived so the DoA gate is reliable."""
        if self.request_type != "Administrative Trip / Document Signing":
            self.trips_this_month = 0
            return
        from frappe.utils import getdate, today, get_first_day, get_last_day, add_days

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
        # [#rvs6ow]
        self.trips_this_month = len(existing) + 1

    def _derive_needs_operations(self):
        """Server-side Delegation-of-Authority derivation.

        Sets ``needs_operations`` when the request's scope crosses the tier
        threshold so the workflow's "Authorize (Regional)" transition is gated
        off (only "Authorize (Operations)", allowed for the Operations tier,
        remains). Derived here — never trusted from the client — so the gate
        cannot be under-stated. Mirrors the previous before_submit tier logic.
        """
        from apex_habitat.apex_core.doctype.salis_settings.salis_settings import get_salis_int

        worker_count = self.worker_count or 0
        trips = self.trips_this_month or 0

        # [#4mmsa5] Tier thresholds read via the zero-trap helper (a blank/0 Single
        # value falls back to the documented default — never trusted as a real 0).
        ops_threshold = get_salis_int("passenger_count_ops_threshold", 20)
        admin_trip_threshold = get_salis_int("admin_trip_ops_threshold", 5)

        self.needs_operations = 1 if (
            (self.request_type == "Inter-City Relocation" and worker_count > ops_threshold)
            or (self.request_type == "Administrative Trip / Document Signing" and trips > admin_trip_threshold)
            or (self.request_type == "Accommodation to Project Shuttle" and self.is_cross_region)
        ) else 0

    # [#d6un3q]
