# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import calendar
import frappe
from frappe.query_builder.functions import Count


def weekly_occupancy_sync() -> None:
    """Recalculate occupancy counters on all Accommodation Rooms and Buildings.

    Runs a full reconciliation pass to correct any counter drift caused by
    out-of-band data changes.
    """
    batch_size = 500

    # [#d7yd9d]
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
            try:
                active = active_by_room.get(room.name, 0)
                capacity = room.bed_capacity or 0
                if active <= 0:
                    new_status = "Available"
                elif capacity and active >= capacity:
                    new_status = "Full"
                else:
                    new_status = "Partially Occupied"

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
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for room {room.name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: room occupancy counters refreshed.")

    # [#qm5tz5]
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
            try:
                total_rooms = rooms_per_building.get(building.name, 0)
                if not total_rooms:
                    # [#qtpe2y]
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
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for building {building.name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: building occupancy counters refreshed.")


def daily_occupancy_snapshot() -> None:
    """Write a daily point-in-time occupancy row per building to the read-only
    Accommodation Occupancy Snapshot engine, so occupancy history/trends survive
    (the live occupancy_percent field is overwritten and keeps no history).

    The per-building inputs (already-snapshotted set, room counts by status,
    active occupants, capacity, cost-per-capacity) are pre-aggregated once via a
    few grouped queries and looked up in memory, instead of issuing ~7
    ``count``/``exists``/``get_value`` calls per building (N+1). Behaviour and the
    one-row-per-building-per-day idempotency guard are preserved."""
    from frappe.utils import today

    snapshot_date = today()
    year = int(snapshot_date[:4])
    days_in_year = 366 if calendar.isleap(year) else 365

    # [#tt1y1j]
    already = {
        r["building"]
        for r in frappe.get_all(
            "Occupancy Snapshot",
            filters={"snapshot_date": snapshot_date},
            fields=["building"],
        )
        if r["building"]
    }

    # [#90367k]
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

    # [#6kydth]
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

    # [#im8xs8]
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
                }).insert(ignore_permissions=True)  # audit-ok
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy snapshot failed for building {building_name}"[:140],
                )
        start += batch_size
    frappe.logger().info("daily_occupancy_snapshot: snapshots written.")
