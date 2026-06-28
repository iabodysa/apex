# Copyright (c) 2026, AFMCO and contributors
"""Shared bulk title-enrichment for Salis board/console/alert readers.

The dispatch board, fuel approval console and operations-alert queue each render
rows that reference a vehicle and a driver by docname and need the human-readable
plate + driver name attached. They all resolved those titles with the same two
bounded lookups (one per referenced DocType) inlined three times.

This module owns that single bulk path. CRITICAL — output-key drift fix: the
three readers had diverged on the plate output key (``vehicle_plate`` on the
dispatch/fuel rows vs ``plate_number`` on the alert rows), so the same logical
value carried two names across the API surface. The canonical key is
``vehicle_plate`` (``plate_number`` is the Salis Vehicle *fieldname*; reusing it
on a trip/alert row was the confusing, drift-prone choice). Every consumer now
reads ``vehicle_plate``.
"""

from __future__ import annotations

import frappe

# Canonical enrichment output keys every consumer reads.
VEHICLE_PLATE_KEY = "vehicle_plate"
DRIVER_NAME_KEY = "driver_name"


def vehicle_driver_titles(rows, *, vehicle_field: str = "vehicle", driver_field: str = "driver"):
    """Attach ``vehicle_plate`` + ``driver_name`` to every row, in bulk, in place.

    Resolves the display titles for each distinct vehicle and driver referenced by
    ``rows`` in two bounded queries (no N+1), then maps them back onto each row.
    The plate falls back to the vehicle docname and the name to the driver docname
    when a title is missing, preserving the readers' prior fallback behaviour.

    ``rows`` is any iterable of mutable mapping rows (``frappe._dict`` or ``dict``).
    ``vehicle_field`` / ``driver_field`` name the source reference fields on a row.
    Returns the same ``rows`` for convenience.
    """
    rows = list(rows)

    vehicle_ids = list({r.get(vehicle_field) for r in rows if r.get(vehicle_field)})
    driver_ids = list({r.get(driver_field) for r in rows if r.get(driver_field)})

    plate_by_vehicle: dict = {}
    if vehicle_ids:
        for v in frappe.get_all(
            "Salis Vehicle",
            filters={"name": ["in", vehicle_ids]},
            fields=["name", "plate_number"],
        ):
            plate_by_vehicle[v.name] = v.get("plate_number")

    name_by_driver: dict = {}
    if driver_ids:
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", driver_ids]},
            fields=["name", "full_name"],
        ):
            name_by_driver[d.name] = d.get("full_name")

    for r in rows:
        vehicle = r.get(vehicle_field)
        driver = r.get(driver_field)
        r[VEHICLE_PLATE_KEY] = plate_by_vehicle.get(vehicle) or vehicle
        r[DRIVER_NAME_KEY] = name_by_driver.get(driver) or driver

    return rows
