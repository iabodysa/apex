# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

ACTIVE_ASSIGNMENT = {"docstatus": 1, "check_out_date": ["is", "not set"]}

_MIX_BUCKET = {"green": "available", "red": "occupied", "amber": "blocked"}


def active_assignment_filters(**extra) -> dict:
    return {**extra, **ACTIVE_ASSIGNMENT}


def room_status(active: int, capacity: int | None) -> str:
    if active <= 0:
        return "Available"
    if capacity and active >= capacity:
        return "Full"
    return "Partially Occupied"


def bed_color(bed_status: str, condition: str, readiness_status: str) -> str:
    if bed_status == "Out of Service" or condition == "Scrapped":
        return "grey"
    if bed_status == "Occupied":
        return "red"
    if bed_status == "Available":
        if readiness_status in ("Ready", "Unknown"):
            return "green"
        if readiness_status in ("Needs Cleaning", "Needs Repair", "Out of Service"):
            return "amber"
    return "grey"


def empty_bed_mix() -> dict:
    return {"total_beds": 0, "available": 0, "occupied": 0, "blocked": 0, "out_of_service": 0}


def tally_bed(mix: dict, color: str) -> None:
    mix["total_beds"] += 1
    mix[_MIX_BUCKET.get(color, "out_of_service")] += 1


def bed_mix_rows(building_names) -> list:
    Bed = frappe.qb.DocType("Bed")
    Room = frappe.qb.DocType("Room")
    return (
        frappe.qb.from_(Bed)
        .left_join(Room)
        .on(Bed.room == Room.name)
        .select(Bed.building, Bed.status.as_("bed_status"), Bed.condition, Room.readiness_status)
        .where(Bed.building.isin(building_names))
        .run(as_dict=True)
    )


def bed_mix(rows, building_names) -> dict:
    mix = {name: empty_bed_mix() for name in building_names}
    for row in rows:
        bucket = mix.get(row.building)
        if bucket is None:
            continue
        tally_bed(bucket, bed_color(row.bed_status, row.condition, row.readiness_status))
    return mix
