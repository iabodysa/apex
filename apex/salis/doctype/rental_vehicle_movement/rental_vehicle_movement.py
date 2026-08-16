# Copyright (c) 2026, afmcoltd
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
from frappe.utils import getdate

from apex.salis.utils import add_timeline_note


class RentalVehicleMovement(Document):
    def validate(self):
        """Validates the vehicle is rented, the daily rate, and the Receipt/Return sequence."""
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

        self._guard_lifecycle()

    def _guard_lifecycle(self):
        """Keep the Receipt/Return sequence sane so the accrual engine's in-service
        window can't be corrupted: a Return needs a prior open Receipt to close,
        and a second Receipt cannot open while one is already open (the vehicle is
        in-service whenever it has a submitted Receipt with no later submitted
        Return). Counts submitted movements only — that is the window the engine
        derives. Skips amendments of this same document."""
        if not (self.vehicle and self.movement_type):
            return
        open_receipt_date = self._open_receipt_date()
        if open_receipt_date is not None:
            if self.movement_type == "Receipt":
                frappe.throw(
                    _("Vehicle {0} already has an open rental Receipt; return it before a new Receipt.").format(
                        self.vehicle
                    )
                )
            if (
                self.movement_type == "Return"
                and self.movement_date
                and getdate(self.movement_date) < getdate(open_receipt_date)
            ):
                frappe.throw(
                    _("Return date cannot be earlier than the open Receipt date ({0}).").format(
                        open_receipt_date
                    )
                )
        elif self.movement_type == "Return":
            frappe.throw(
                _("Vehicle {0} has no open rental Receipt to return.").format(self.vehicle)
            )

    def _open_receipt_date(self):
        """The movement_date of the vehicle's currently-open Receipt (a submitted
        Receipt with no later submitted Return), or None when not in-service.
        Excludes this document and its amendment lineage so re-amending a movement
        does not see itself."""
        exclude = [n for n in (self.name, self.amended_from) if n]
        movements = frappe.get_all(
            "Rental Vehicle Movement",
            filters={
                "vehicle": self.vehicle,
                "docstatus": 1,
                "name": ["not in", exclude or [""]],
            },
            fields=["movement_type", "movement_date", "creation"],
            order_by="movement_date asc, creation asc",
        )
        open_receipt_date = None
        for m in movements:
            if m.movement_type == "Receipt":
                open_receipt_date = m.movement_date
            elif m.movement_type == "Return":
                open_receipt_date = None
        return open_receipt_date

    def on_submit(self):
        """Adds a vehicle timeline note recording the rental receipt or return."""
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental {0} via {1} (office {2}).").format(
                _(self.movement_type), self.name, self.rental_office or _("n/a")
            ),
        )

    def on_cancel(self):
        """Adds a vehicle timeline note and reverses any accrual this Receipt produced.

        Only a Receipt ever names a Rental Accrual Ledger row's ``source_name`` (see
        ``rental_engine._currently_received``), so a Return never has ledger rows to
        reverse. Without this, the accrued days a cancelled Receipt justified would
        outlive it and still be there for the next settlement to claim.
        """
        if self.movement_type == "Receipt":
            from apex.salis.rental_engine import reverse_rental_accrual

            reverse_rental_accrual("Rental Vehicle Movement", self.name)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental movement {0} ({1}) cancelled.").format(
                self.name, _(self.movement_type)
            ),
        )
