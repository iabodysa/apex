# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today


def validate_driver_has_no_planned_trips(driver):
    trips = planned_trips_for_driver(driver)
    if not trips:
        return
    frappe.throw(
        _("{0} still has {1} planned trip(s): {2}. Assign another driver to them first.").format(
            frappe.db.get_value("Salis Driver", driver, "full_name") or driver,
            len(trips),
            ", ".join(trips[:5]) + ("…" if len(trips) > 5 else ""),
        ),
        title=_("Reassign the trips first"),
    )


def planned_trips_for_driver(driver, on_or_after=None):
    if not driver:
        return []
    return frappe.get_all(
        "Dispatch Trip",
        filters={
            "driver": driver,
            "docstatus": 0,
            "status": "Planned",
            "trip_date": [">=", getdate(on_or_after) if on_or_after else getdate(today())],
        },
        pluck="name",
        order_by="trip_date asc",
    )


def dispatched_trips_for_driver(driver):
    if not driver:
        return []
    return frappe.get_all(
        "Dispatch Trip",
        filters={"driver": driver, "docstatus": 0, "status": "Dispatched"},
        pluck="name",
    )
