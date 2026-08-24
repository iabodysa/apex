# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import today

_CLEANING_SAVEPOINT = "cleaning_log_insert"

def daily_cleaning_log_generator() -> None:
    cleaning_date = today()
    logger = frappe.logger()

    already = {
        r["building"]
        for r in frappe.get_all(
            "Cleaning Log",
            filters={"cleaning_date": cleaning_date, "docstatus": ["!=", 2]},
            fields=["building"],
        )
        if r["building"]
    }

    rooms_by_building: dict[str, list[str]] = {}
    for r in frappe.get_all(
        "Room",
        filters={"building": ["is", "set"]},
        fields=["name", "building"],
    ):
        rooms_by_building.setdefault(r["building"], []).append(r["name"])

    created = 0
    start = 0
    batch_size = 500
    while True:
        buildings = frappe.get_all(
            "Building",
            filters={"status": "Active"},
            pluck="name",
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for building in buildings:
            if building in already:
                continue
            rooms = rooms_by_building.get(building) or []

            frappe.db.savepoint(_CLEANING_SAVEPOINT)
            try:
                log = frappe.get_doc({
                    "doctype": "Cleaning Log",
                    "building": building,
                    "cleaning_date": cleaning_date,
                    "room_details": [{"room": room} for room in rooms],
                })
                log.insert()
            except Exception:
                frappe.db.rollback(save_point=_CLEANING_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Daily cleaning log generation failed for {building}"[:140],
                )
            else:
                frappe.db.release_savepoint(_CLEANING_SAVEPOINT)
                created += 1

        start += batch_size

    logger.info(f"daily_cleaning_log_generator: created {created} draft cleaning log(s).")

