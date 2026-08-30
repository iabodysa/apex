# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.salis.utils import lock_vehicle


class FuelQuota(Document):
    def validate(self):
        self._guard_duplicate()
        if flt(self.monthly_litres) <= 0:
            frappe.throw(_("Monthly litres must be greater than zero."))
        monthly = self.monthly_litres or 0
        consumed = self.consumed_litres or 0
        if monthly and consumed > monthly:
            frappe.msgprint(
                _("Consumed litres ({0}) exceed the monthly quota ({1}).").format(
                    consumed, monthly
                ),
                indicator="orange",
                title=_("Quota Exceeded"),
            )

    def _guard_duplicate(self):
        if not (self.vehicle and self.period_month):
            return
        lock_vehicle(self.vehicle)
        dup = frappe.db.exists(
            "Fuel Quota",
            {
                "vehicle": self.vehicle,
                "period_month": self.period_month,
                "docstatus": ["<", 2],
                "name": ["!=", self.name or ""],
            },
        )
        if dup:
            frappe.throw(
                _("Fuel Quota {0} already exists for vehicle {1} in period {2}.").format(
                    dup, self.vehicle, self.period_month
                )
            )


def on_doctype_update():
    frappe.db.add_unique(
        "Fuel Quota",
        ["vehicle", "period_month", "docstatus"],
        constraint_name="uq_fuel_quota_vehicle_period",
    )
