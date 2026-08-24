# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex.salis.rental_engine import reverse_rental_accrual
from apex.salis.utils import add_timeline_note


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

        self._guard_lifecycle()

    def _guard_lifecycle(self):
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
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental {0} via {1} (office {2}).").format(
                _(self.movement_type), self.name, self.rental_office or _("n/a")
            ),
        )

    def on_cancel(self):
        if self.movement_type == "Receipt":
            reverse_rental_accrual("Rental Vehicle Movement", self.name)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Rental movement {0} ({1}) cancelled.").format(
                self.name, _(self.movement_type)
            ),
        )
