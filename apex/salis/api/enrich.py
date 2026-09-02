# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

VEHICLE_PLATE_KEY = "vehicle_plate"
DRIVER_NAME_KEY = "driver_name"


def vehicle_driver_titles(rows, *, vehicle_field: str = "vehicle", driver_field: str = "driver"):
    rows = list(rows)

    vehicle_ids = list({r.get(vehicle_field) for r in rows if r.get(vehicle_field)})
    driver_ids = list({r.get(driver_field) for r in rows if r.get(driver_field)})

    plate_by_vehicle: dict = {}
    if vehicle_ids:
        for v in frappe.get_list(
            "Salis Vehicle",
            filters={"name": ["in", vehicle_ids]},
            fields=["name", "plate_number"],
        ):
            plate_by_vehicle[v.name] = v.get("plate_number")

    name_by_driver: dict = {}
    if driver_ids:
        for d in frappe.get_list(
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
