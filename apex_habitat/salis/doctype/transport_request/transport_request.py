"""Transport Request controller.

Transitions are owned by the native **Transport Request Workflow** (see
``salis/workflow/transport_request_workflow/``), not by this controller. The
workflow enforces the role per transition, the Segregation-of-Duties gate
(approver != requester) and the Delegation-of-Authority tier escalation via its
transition ``condition``s.

This controller keeps only the *data* guards: the service_line -> request_type
pairing, the per-request-type required fields/evidence, and the **server-side
DoA derivation** that sets ``needs_operations`` so the workflow's tier gate
cannot be under-stated by a client. ``worker_count`` and ``trips_this_month``
are likewise derived server-side, never trusted from the form.
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

# Allowed request types per service line (two-division service model).
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
        # The Select still carries the known states for filtering/colour, but the
        # workflow owns *transitions* — this only rejects an unknown value.
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

        # Trips-this-month is server-derived (not a trusted manual input), so the
        # >5-trips/month DoA tier gate cannot be under-stated.
        self._derive_trips_this_month()

        # The DoA tier flag is derived from the (server-set) scope figures so the
        # workflow's tier condition cannot be circumvented by a crafted payload.
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
        # +1 to include the request currently being validated/submitted.
        self.trips_this_month = len(existing) + 1

    def _derive_needs_operations(self):
        """Server-side Delegation-of-Authority derivation.

        Sets ``needs_operations`` when the request's scope crosses the tier
        threshold so the workflow's "Authorize (Regional)" transition is gated
        off (only "Authorize (Operations)", allowed for the Operations tier,
        remains). Derived here — never trusted from the client — so the gate
        cannot be under-stated. Mirrors the previous before_submit tier logic.
        """
        worker_count = self.worker_count or 0
        trips = self.trips_this_month or 0

        # Worker-count escalation threshold is configurable via Salis Settings so
        # the DoA gate can be tuned without a code change. Default to 20 if unset.
        ops_threshold = frappe.db.get_single_value(
            "Salis Settings", "passenger_count_ops_threshold"
        )
        if not ops_threshold:
            ops_threshold = 20

        self.needs_operations = 1 if (
            (self.request_type == "Inter-City Relocation" and worker_count > ops_threshold)
            or (self.request_type == "Administrative Trip / Document Signing" and trips > 5)
            or (self.request_type == "Accommodation to Project Shuttle" and self.is_cross_region)
        ) else 0

    # Transitions, the SoD gate, and the DoA tier gate are enforced by the native
    # Transport Request Workflow. Submit/cancel are recorded natively
    # (Version track_changes + the automatic Workflow comment).
