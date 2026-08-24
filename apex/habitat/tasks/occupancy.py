# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import calendar
import frappe
from frappe.query_builder.functions import Count
from frappe.utils import today

from apex.habitat.utils.occupancy import room_status

_ROW_SAVEPOINT = "occupancy_row"


def weekly_occupancy_sync() -> None:
    batch_size = 500

    HA = frappe.qb.DocType("Housing Assignment")
    active_by_room = {
        r["room"]: int(r["n"] or 0)
        for r in (
            frappe.qb.from_(HA)
            .select(HA.room, Count(HA.name).as_("n"))
            .where(HA.docstatus == 1)
            .where((HA.check_out_date.isnull()) | (HA.check_out_date == ""))
            .where(HA.room.isnotnull())
            .groupby(HA.room)
        ).run(as_dict=True)
    }

    start = 0
    while True:
        rooms = frappe.get_all(
            "Room",
            fields=["name", "bed_capacity"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not rooms:
            break

        for room in rooms:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                active = active_by_room.get(room.name, 0)
                new_status = room_status(active, room.bed_capacity)

                frappe.db.set_value(
                    "Room",
                    room.name,
                    {
                        "current_occupancy": active,
                        "status": new_status,
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for room {room.name}"[:140],
                )

        start += batch_size

    Room = frappe.qb.DocType("Room")
    rooms_per_building = {
        r["building"]: int(r["n"] or 0)
        for r in (
            frappe.qb.from_(Room)
            .select(Room.building, Count(Room.name).as_("n"))
            .where(Room.building.isnotnull())
            .groupby(Room.building)
        ).run(as_dict=True)
    }
    active_by_building = {
        r["building"]: int(r["n"] or 0)
        for r in (
            frappe.qb.from_(HA)
            .select(HA.building, Count(HA.name).as_("n"))
            .where(HA.docstatus == 1)
            .where((HA.check_out_date.isnull()) | (HA.check_out_date == ""))
            .where(HA.building.isnotnull())
            .groupby(HA.building)
        ).run(as_dict=True)
    }

    start = 0
    while True:
        buildings = frappe.get_all(
            "Building",
            fields=["name", "total_capacity"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for building in buildings:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                total_rooms = rooms_per_building.get(building.name, 0)
                if not total_rooms:
                    continue

                active = active_by_building.get(building.name, 0)
                total_capacity = building.total_capacity or 0
                occupancy_pct = (active / total_capacity * 100) if total_capacity else 0.0
                frappe.db.set_value(
                    "Building",
                    building.name,
                    {
                        "current_occupants": active,
                        "occupancy_percent": round(occupancy_pct, 2),
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for building {building.name}"[:140],
                )

        start += batch_size


def daily_occupancy_snapshot() -> None:
    snapshot_date = today()
    year = int(snapshot_date[:4])
    days_in_year = 366 if calendar.isleap(year) else 365

    already = {
        r["building"]
        for r in frappe.get_all(
            "Occupancy Snapshot",
            filters={"snapshot_date": snapshot_date},
            fields=["building"],
        )
        if r["building"]
    }

    Room = frappe.qb.DocType("Room")
    rooms_by_building: dict = {}
    for r in (
        frappe.qb.from_(Room)
        .select(Room.building, Room.status, Count(Room.name).as_("n"))
        .where(Room.building.isnotnull())
        .groupby(Room.building, Room.status)
    ).run(as_dict=True):
        bucket = rooms_by_building.setdefault(r["building"], {"_total": 0})
        bucket[r["status"]] = int(r["n"] or 0)
        bucket["_total"] += int(r["n"] or 0)

    HA = frappe.qb.DocType("Housing Assignment")
    active_by_building = {
        r["building"]: int(r["n"] or 0)
        for r in (
            frappe.qb.from_(HA)
            .select(HA.building, Count(HA.name).as_("n"))
            .where(HA.docstatus == 1)
            .where((HA.check_out_date.isnull()) | (HA.check_out_date == ""))
            .where(HA.building.isnotnull())
            .groupby(HA.building)
        ).run(as_dict=True)
    }

    building_meta = {
        b["name"]: b
        for b in frappe.get_all(
            "Building",
            fields=["name", "total_capacity", "annual_cost_per_capacity"],
        )
    }

    start = 0
    batch_size = 500
    while True:
        building_names = frappe.get_all(
            "Building", pluck="name",
            limit_start=start, limit_page_length=batch_size,
        )
        if not building_names:
            break
        for building_name in building_names:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                if building_name in already:
                    continue
                room_bucket = rooms_by_building.get(building_name)
                total_rooms = room_bucket["_total"] if room_bucket else 0
                if not total_rooms:
                    continue
                active = active_by_building.get(building_name, 0)
                meta = building_meta.get(building_name) or {}
                total_capacity = meta.get("total_capacity") or 0
                occ_pct = round(active / total_capacity * 100, 2) if total_capacity else 0.0
                available_capacity = max(total_capacity - active, 0)

                annual_cost_per_capacity = meta.get("annual_cost_per_capacity") or 0.0
                cost_bleeding = round(available_capacity * (annual_cost_per_capacity / days_in_year), 2)

                frappe.get_doc({
                    "doctype": "Occupancy Snapshot",
                    "snapshot_date": snapshot_date,
                    "building": building_name,
                    "active_occupants": active,
                    "total_capacity": total_capacity,
                    "occupancy_percent": occ_pct,
                    "available_capacity": available_capacity,
                    "cost_bleeding": cost_bleeding,
                    "full_rooms": room_bucket.get("Full", 0),
                    "partial_rooms": room_bucket.get("Partially Occupied", 0),
                    "available_rooms": room_bucket.get("Available", 0),
                }).insert()
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy snapshot failed for building {building_name}"[:140],
                )
        start += batch_size
