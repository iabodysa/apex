# Copyright (c) 2026, afmcoltd
"""What a driver still holds when somebody tries to stop him.

Stopping a driver — a Driver Suspension, or a Driver Clearance submitted as Cleared —
moves ``Salis Driver.status`` out of Active and nothing downstream rewrites a trip that
already names him. ``salis.utils.rider_block_reason`` gates a vehicle, a fuel request and
a handover, and none of the three is a trip, so a planned trip keeps a stopped driver's
name until the morning it runs.

A Link field that asks WHO WILL DO THIS WORK carries ``link_filters`` pinning its picker to
Active, on Salis Driver and on Salis Vehicle alike, because offering a stopped record there
offers a choice the flow refuses later. A field that NAMES a record rather than books it —
the clearance about him, the incident that stopped him, the ledger row he already earned, a
case that outlives the stop — stays unfiltered. The split is decided by that question and
by nothing else, so a new Link field is graded by asking it rather than by copying a
neighbour.

``link_filters`` shapes the PICKER and nothing else: ``link.js:600`` applies it inside the
form control, so no API path is narrowed by it and every server-side refusal stays where it is.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today


def validate_driver_has_no_planned_trips(driver):
    """Refuse the stop while planned trips still name ``driver``, listing them.

    Only a PLANNED trip refuses. A Dispatched trip is a vehicle already in motion and a
    stop raised after an accident cannot wait for it, so it is reported to the supervisor
    instead — see ``dispatched_trips_for_driver`` and its call site.
    """
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
    """Every not-yet-dispatched trip still naming ``driver`` from ``on_or_after``.

    ``docstatus 0`` with ``status = Planned`` is the one state a trip's driver can be
    changed in without touching a submitted document, which is what makes it refusable.
    """
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
    """Every trip ``driver`` is already running. Reported, never used to refuse."""
    if not driver:
        return []
    return frappe.get_all(
        "Dispatch Trip",
        filters={"driver": driver, "docstatus": 0, "status": "Dispatched"},
        pluck="name",
    )
