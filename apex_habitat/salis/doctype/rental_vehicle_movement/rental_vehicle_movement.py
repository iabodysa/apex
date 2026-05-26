"""Rental Vehicle Movement controller.

Captures the Receipt/Return lifecycle of a rented vehicle from a Rental Office.
There is no explicit ``accrual_active`` state stored on the vehicle: a vehicle
is considered in-service whenever it has a submitted Receipt with no later
submitted Return. The Rental Accrual Ledger engine derives that window directly
by querying these movements (see ``rental_engine.daily_rental_accrual``).

Posts NO General Ledger / accounting entry of any kind.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.salis_lib import log_activity


class RentalVehicleMovement(Document):
    def validate(self):
        if self.vehicle:
            ownership = frappe.db.get_value("Salis Vehicle", self.vehicle, "ownership")
            if ownership != "Rented":
                frappe.throw(
                    _("Vehicle {0} is not a rented vehicle (ownership is {1}).").format(
                        self.vehicle, _(ownership or "Owned")
                    )
                )

        if self.movement_type == "Receipt" and not self.daily_rate:
            frappe.throw(_("Daily Rate is required on a Receipt movement."))

        if self.movement_type == "Receipt" and self.daily_rate is not None and self.daily_rate < 0:
            frappe.throw(_("Daily Rate cannot be negative."))

    def on_submit(self):
        # Receipt starts accrual eligibility; Return ends it. The engine reads
        # these submitted movements by date — no flag is written here.
        action = (
            "Rental Vehicle Received"
            if self.movement_type == "Receipt"
            else "Rental Vehicle Returned"
        )
        log_activity(
            action=action,
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={
                "movement": self.name,
                "movement_type": self.movement_type,
                "rental_office": self.rental_office,
                "movement_date": str(self.movement_date) if self.movement_date else None,
                "daily_rate": self.daily_rate,
            },
        )

    def on_cancel(self):
        log_activity(
            action="Rental Vehicle Movement Cancelled",
            entity_type="Salis Vehicle",
            entity_name=self.vehicle,
            details={"movement": self.name, "movement_type": self.movement_type},
        )
