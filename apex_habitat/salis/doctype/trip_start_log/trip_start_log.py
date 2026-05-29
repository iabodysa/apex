"""Trip Start Log controller.

Execution record for a worker-transport trip (the Workers division of Salis,
branded "Masar"). It captures, against a Dispatch Trip, the start/end times, the
expected headcount, and a boarding-event child table (who boarded, where, when,
and how — QR or Manual). Registered workers come from the linked Transport
Request's manifest; unregistered contractors/temp hires are supported on the
child row (``is_unregistered``).

Boundary: this is a purely operational headcount record. It posts **no GL Entry
/ Journal Entry** and creates no accounting documents — consistent with the
Salis no-financial-impact rule. The controller is light: it derives the counts
(``expected_count`` from the request manifest, ``boarded_count`` from the child
rows — both read-only, never hand-set) and validates each boarding row; it never
moves money and owns no cross-document side-effects.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TripStartLog(Document):
    def validate(self):
        self._resolve_trip_context()
        self._validate_boarding_rows()
        self._derive_counts()
        self._validate_times()

    def _resolve_trip_context(self):
        """Backfill Transport Request / Route Plan from the Dispatch Trip when the
        fetch did not populate them (e.g. a row built in code), so the manifest
        and project-scoping chain stay intact."""
        if not self.dispatch_trip:
            return
        if not self.transport_request:
            self.transport_request = frappe.db.get_value(
                "Dispatch Trip", self.dispatch_trip, "transport_request"
            )
        if not self.route_plan:
            self.route_plan = frappe.db.get_value(
                "Dispatch Trip", self.dispatch_trip, "route_plan"
            )

    def _validate_boarding_rows(self):
        """Each boarding row identifies exactly one worker: a registered Employee
        (``worker``) OR an unregistered contractor/temp (``is_unregistered`` with a
        name or contractor id). This keeps the headcount honest and the
        unregistered path explicit."""
        for row in self.boarding_events:
            if row.is_unregistered:
                if not (row.worker_name or row.contractor_id):
                    frappe.throw(
                        _(
                            "Boarding row #{0}: an unregistered worker needs a name or a contractor/temp id."
                        ).format(row.idx)
                    )
            elif not row.worker:
                frappe.throw(
                    _(
                        "Boarding row #{0}: select a Worker, or tick 'Unregistered' and give a name/id."
                    ).format(row.idx)
                )

    def _derive_counts(self):
        """Derive both counts server-side; neither is hand-set.

        - ``expected_count`` = the linked Transport Request's registered worker
          count (its manifest size).
        - ``boarded_count`` = the number of boarding event rows.
        """
        self.boarded_count = len(self.boarding_events or [])
        expected = 0
        if self.transport_request:
            expected = (
                frappe.db.get_value(
                    "Transport Request", self.transport_request, "worker_count"
                )
                or 0
            )
        self.expected_count = expected

    def _validate_times(self):
        """End cannot precede start when both are set."""
        if self.start_datetime and self.end_datetime:
            if self.end_datetime < self.start_datetime:
                frappe.throw(
                    _("End Datetime cannot be earlier than Start Datetime.")
                )
