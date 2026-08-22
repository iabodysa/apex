# Copyright (c) 2026, afmcoltd
"""Fuel Daily Log controller.

Non-submittable daily fuel consumption record. Light validation; an audit entry
is written once on creation (the doc is not submittable, so there is no submit
event to hook).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

from apex.apex_core.utils.company import display_currency

from apex.salis.utils import add_timeline_note


class FuelDailyLog(Document):
    def validate(self):
        """Rejects an odometer reading that runs backwards."""
        self._refuse_an_odometer_that_runs_backwards()

    def _refuse_an_odometer_that_runs_backwards(self):
        """A reading may not be lower than the last one taken on or before its own date.

        Rejecting only a NEGATIVE reading let a typo through, and a typo here is not
        cosmetic: the weekly utilisation summary scores an inverted pair as zero distance
        (``salis/tasks/vehicle.py:156-160``) and says nothing, so the vehicle simply
        under-reports. hrms enforces the same rule in eighteen lines at
        ``hrms/hr/doctype/vehicle_log/vehicle_log.py:12-29``, but against a denormalised
        ``last_odometer`` it advances on submit and rewinds on cancel. This log is not
        submittable and can be deleted, so the comparison is made against the logs
        themselves — there is no second copy to keep in step, and a late entry for an
        earlier date is judged against its own day rather than against the newest.
        """
        if self.odometer is None or not self.vehicle or not self.log_date:
            return
        previous = frappe.db.get_value(
            "Fuel Daily Log",
            {
                "vehicle": self.vehicle,
                "log_date": ["<=", self.log_date],
                "name": ["!=", self.name or ""],
                "odometer": [">", 0],
            },
            "odometer",
            order_by="log_date desc, creation desc",
        )
        if previous is not None and flt(self.odometer) < flt(previous):
            frappe.throw(
                _("Odometer {0} is lower than the last reading for this vehicle ({1}).").format(
                    flt(self.odometer), flt(previous)
                )
            )

    def after_insert(self):
        """Adds a vehicle timeline note recording the logged litres and amount."""
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Fuel daily log {0}: {1} L, {2}.").format(
                self.name,
                self.litres,
                fmt_money(self.amount, currency=display_currency("Salis")),
            ),
        )

    def on_trash(self):
        """Reverses this log's entry from the fuel consumption ledger when the row is deleted."""
        from apex.salis.fuel_engine import reverse_fuel_ledger

        reverse_fuel_ledger("Fuel Daily Log", self.name)
