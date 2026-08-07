# Copyright (c) 2026, AFMCO and contributors
"""Occupancy primitives shared by the housing desks and the Building controller.

Active occupancy has ONE definition here — a submitted Housing Assignment whose
``check_out_date`` is not set — so a change to the rule cannot land in one reader
and be missed by another. The bed-colour rule and its tally take plain values and
return values, so both are exercisable without a bench or a database.
"""

from __future__ import annotations

import frappe

ACTIVE_ASSIGNMENT = {"docstatus": 1, "check_out_date": ["is", "not set"]}

_MIX_BUCKET = {"green": "available", "red": "occupied", "amber": "blocked"}


def active_assignment_filters(**extra) -> dict:
    """Filters matching LIVE occupancy, plus whatever narrows it (bed, building,
    party). The active-occupancy pair always wins over a caller's key."""
    return {**extra, **ACTIVE_ASSIGNMENT}


def room_status(active: int, capacity: int | None) -> str:
    """The occupancy ladder for a Room: Available, Partially Occupied, or Full.

    A ROOM WITH NO DECLARED CAPACITY IS NEVER FULL. Zero or null bed_capacity means the
    capacity is unknown — the room has not been set up yet — not that the room holds
    nobody, so the first resident must not read as a room that can take no more. The
    honest answer while the ceiling is unknown is Partially Occupied: someone is in
    there, and how many more fit is not recorded.

    This is the product decision the two former writers disagreed on. The live handler
    used ``active >= (capacity or 0)``, which made an undeclared room Full on its first
    occupant; the weekly job used ``capacity and active >= capacity``, which did not. The
    room's status therefore flipped every time the sync ran. The weekly job's answer is
    the one kept, for the reason above rather than because it ran last.

    Takes plain values and returns a value, so it is exercisable without a database."""
    if active <= 0:
        return "Available"
    if capacity and active >= capacity:
        return "Full"
    return "Partially Occupied"


def bed_color(bed_status: str, condition: str, readiness_status: str) -> str:
    """Resolve the housing board bed color. First matching rule wins (top-down).

    1. Out of Service / Scrapped  -> grey  (disabled)
    2. Occupied                   -> red   (active occupant)
    3. Available + room Ready/Unknown            -> green (clickable)
    4. Available + room not ready (cleaning/repair/oos) -> amber (warning)
    5. fallback                   -> grey
    """
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
    """A zeroed bed mix: the five counts every board reports."""
    return {"total_beds": 0, "available": 0, "occupied": 0, "blocked": 0, "out_of_service": 0}


def tally_bed(mix: dict, color: str) -> None:
    """Fold one bed's colour into a mix. Any colour outside the named three counts
    as out of service, which is what grey means on the board."""
    mix["total_beds"] += 1
    mix[_MIX_BUCKET.get(color, "out_of_service")] += 1


def bed_mix_rows(building_names) -> list:
    """ONE bounded Bed/Room aggregate covering every building in scope.

    Link fields carry no index by default, so the boards read all their beds in a
    single pass rather than one query per building."""
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
    """Per-building bed mix folded from the aggregate rows.

    A building with no bed row still gets a zeroed entry; a row belonging to a
    building outside ``building_names`` is ignored."""
    mix = {name: empty_bed_mix() for name in building_names}
    for row in rows:
        bucket = mix.get(row.building)
        if bucket is None:
            continue
        tally_bed(bucket, bed_color(row.bed_status, row.condition, row.readiness_status))
    return mix
