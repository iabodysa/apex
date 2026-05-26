"""Dispatch Trip controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import lock_vehicle, log_activity

# Allowed forward status transitions. Cancellation is allowed from any state.
_ALLOWED_TRANSITIONS = {
    "Planned": {"Planned", "Dispatched", "Cancelled"},
    "Dispatched": {"Dispatched", "Completed", "Cancelled"},
    "Completed": {"Completed", "Cancelled"},
    "Cancelled": {"Cancelled"},
}


class DispatchTrip(Document):
    def validate(self):
        self._enforce_status_flow()
        self._validate_odometer()

    def _enforce_status_flow(self):
        before = self.get_doc_before_save()
        if not before or not before.status:
            return
        old, new = before.status, self.status
        if new == old:
            return
        if new not in _ALLOWED_TRANSITIONS.get(old, set()):
            frappe.throw(
                _("Illegal status change from {0} to {1}.").format(_(old), _(new))
            )

    def _validate_odometer(self):
        if self.odometer_end is not None and self.odometer_start is not None:
            if self.odometer_end < self.odometer_start:
                frappe.throw(
                    _("Trip end odometer ({0}) cannot be less than start ({1}).").format(
                        self.odometer_end, self.odometer_start
                    )
                )

    def on_submit(self):
        if self.status == "Completed" and self.odometer_end and self.vehicle:
            lock_vehicle(self.vehicle)
            current = frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            if self.odometer_end > current:
                frappe.db.set_value(
                    "Salis Vehicle", self.vehicle, "odometer", self.odometer_end
                )
            log_activity(
                action="Trip Completed",
                entity_type="Salis Vehicle",
                entity_name=self.vehicle,
                details={"trip": self.name, "odometer_end": self.odometer_end},
            )
