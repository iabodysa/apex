# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import get_driver_for_user


class TripStartLog(Document):
    def validate(self):
        self._validate_boarding_rows()
        self._derive_counts()
        self._validate_times()
        self._check_driver_ownership()

    def _check_driver_ownership(self):
        driver = get_driver_for_user()
        if not driver:
            return
        if self.driver and self.driver != driver:
            frappe.throw(
                _("You can only save Trip Start Logs assigned to your own driver record."),
                frappe.PermissionError,
            )

    def _validate_boarding_rows(self):
        seen_workers = set()
        seen_unregistered = set()
        for row in self.boarding_events:
            if row.is_unregistered:
                if not (row.worker_name or row.contractor_id):
                    frappe.throw(
                        _(
                            "Boarding row #{0}: an unregistered worker needs a name or a contractor/temp id."
                        ).format(row.idx)
                    )
                key = (row.contractor_id or row.worker_name or "").strip().casefold()
                if key:
                    if key in seen_unregistered:
                        frappe.throw(
                            _(
                                "Boarding row #{0}: this worker has already boarded on this trip."
                            ).format(row.idx)
                        )
                    seen_unregistered.add(key)
            elif not row.worker:
                frappe.throw(
                    _(
                        "Boarding row #{0}: select a Worker, or tick 'Unregistered' and give a name/id."
                    ).format(row.idx)
                )
            else:
                if row.worker in seen_workers:
                    frappe.throw(
                        _(
                            "Boarding row #{0}: worker {1} has already boarded on this trip."
                        ).format(row.idx, row.worker)
                    )
                seen_workers.add(row.worker)

    def _derive_counts(self):
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
        if self.start_datetime and self.end_datetime:
            if self.end_datetime < self.start_datetime:
                frappe.throw(
                    _("End Datetime cannot be earlier than Start Datetime.")
                )
