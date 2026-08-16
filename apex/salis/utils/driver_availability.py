# Copyright (c) 2026, afmcoltd
"""What a driver still holds when somebody tries to stop him.

Stopping a driver — a Driver Suspension, or a Driver Clearance submitted as Cleared —
moves ``Salis Driver.status`` out of Active and nothing downstream rewrites a trip that
already names him. ``salis.utils.rider_block_reason`` gates a vehicle, a fuel request and
a handover, and none of the three is a trip, so a planned trip keeps a stopped driver's
name until the morning it runs.

Thirty Link fields point at Salis Driver. A field that asks WHO WILL DO THIS WORK carries
``link_filters`` pinning the picker to Active, because offering a stopped driver there is
offering a choice the flow refuses later:

    Dispatch Trip.driver · Driver Suspension.driver · Fuel Request.driver ·
    Fuel Quota.driver · Route Assignment.driver · Route Plan.driver ·
    Salis Vehicle.current_driver · Transport Request.assigned_driver ·
    Vehicle Assignment.driver · Vehicle Handover.to_driver

Every other field names a driver who may legitimately be stopped, and stays unfiltered:

    Driver Clearance.driver           clearing a stopped driver is the whole document
    Vehicle Handover.from_driver      the handover exists BECAUSE he stopped
    Vehicle Incident.driver           the incident is usually why he stopped
    Vehicle Incident.previous_driver  historical by definition
    Vehicle Suspension.related_driver the vehicle's holder, whatever his own state
    Driver Attendance.driver          a day already worked, often entered after the stop
    Fuel Exception Case · Movement Cost Recovery · Vehicle Damage Write-Off ·
    Salis Payment Request             a case raised against him, which outlives the stop
    Fuel Claim · Fuel Consumption Ledger · Fuel Daily Log · Trip Fulfilment Ledger ·
    Trip Start Log · Boarding Scan Log · Passenger Manifest ·
    Portal Push Subscription          machine-written history
    Masar Worker Token.driver         an issued identity, read long after it lapses
    Issue.custom_driver               a complaint may name any driver

Salis Vehicle is graded the same way and by the same rule. Filtered to Active:

    Dispatch Trip.vehicle · Fuel Quota.vehicle · Fuel Request.vehicle ·
    Route Assignment.vehicle · Route Plan.vehicle · Salis Driver.current_vehicle ·
    Transport Request.assigned_vehicle · Vehicle Assignment.vehicle ·
    Vehicle Handover.vehicle

Left unfiltered, and why:

    Vehicle Suspension.vehicle        a vehicle Under Maintenance can still be stopped
    Wash Request.vehicle              a stopped vehicle is still washed
    Driver Clearance.assigned_vehicle a read-only snapshot of what he held
    Driver Suspension.related_vehicle the vehicle being released, in any state
    Vehicle Incident.vehicle          the incident is why it stopped
    Vehicle Damage Write-Off · Fuel Exception Case · Movement Cost Recovery ·
    Salis Payment Request             a case that outlives the stop
    Rental Accrual Ledger · Rental Settlement Item · Rental Vehicle Movement
                                      a rented vehicle is often already Released
    Fuel Claim · Fuel Consumption Ledger · Fuel Daily Log · Trip Fulfilment Ledger ·
    Trip Start Log · Passenger Manifest · Vehicle Utilisation Snapshot
                                      machine-written history

``link_filters`` shapes the PICKER and nothing else: ``link.js:600`` applies it inside the
form control, so no API path is narrowed by it and every server-side refusal stays where
it is.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, today


def refuse_to_stop_a_driver_who_still_holds_planned_trips(driver):
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
