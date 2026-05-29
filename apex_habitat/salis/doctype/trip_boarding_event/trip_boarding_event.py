"""Trip Boarding Event — child row of Trip Start Log.

One row per worker boarding the trip: either a registered worker (Employee) or
an unregistered contractor/temp hire (``is_unregistered`` + ``contractor_id`` /
``worker_name``). Carries the stop it happened at, the timestamp and the capture
``method`` (QR | Manual). Validation lives on the parent (Trip Start Log) so the
whole manifest is checked together; this controller is intentionally thin.
"""

from __future__ import annotations

from frappe.model.document import Document


class TripBoardingEvent(Document):
    pass
