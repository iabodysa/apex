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

from apex_habitat.salis.salis_lib import add_timeline_note


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
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental {0} via {1} (office {2}).").format(
                _(self.movement_type), self.name, self.rental_office or _("n/a")
            ),
        )

    def on_cancel(self):
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental movement {0} ({1}) cancelled.").format(
                self.name, _(self.movement_type)
            ),
        )
