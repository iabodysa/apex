# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

from apex.apex_core.utils.company import display_currency

from apex.salis.fuel_engine import reverse_fuel_ledger
from apex.salis.utils import add_timeline_note


class FuelDailyLog(Document):
    def validate(self):
        self._refuse_an_odometer_that_runs_backwards()

    def _refuse_an_odometer_that_runs_backwards(self):
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
        reverse_fuel_ledger("Fuel Daily Log", self.name)
