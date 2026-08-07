# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

_CLEANING_SAVEPOINT = "cleaning_log_insert"


def daily_cleaning_log_generator() -> None:
    """Auto-create today's draft Cleaning Log for every ACTIVE building, so
    housing cleaning becomes a system-of-record instead of relying on a
    supervisor to remember to open a log.

    For each ACTIVE Building (``status == "Active"``) with at least
    one room, a draft Cleaning Log dated today is created if one does not already
    exist, with its ``room_details`` pre-populated from the building's rooms ready
    to mark. The supervisor then marks each room, attaches the required area-photo
    evidence, and submits — submit posts the immutable Cleaning Compliance Ledger.
    The log is left a DRAFT (never auto-submitted): ``CleaningLog.before_submit``
    demands area-photo evidence a system stub cannot supply, and an unmarked room
    posts as not-compliant (``cleaned=0``), which is exactly the audit signal a
    forgotten/unfilled day should carry.

    Idempotent — one Cleaning Log per (building, cleaning_date), mirroring
    ``daily_occupancy_snapshot``'s one-row-per-building-per-day guard: the set of
    buildings already logged today is fetched once and looked up in memory.
    Rooms are pre-aggregated by building in one query (no N+1). Per-building error
    isolation; paginated 500/batch.
    """
    from frappe.utils import today

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
                log.insert(ignore_permissions=True)
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


def auto_create_cleaning_logs() -> None:
    """The spec name for the daily cleaning log. One implementation, not two.

    Their target sets also differed: this one took Active buildings with a
    ``responsible_supervisor``, the other took Active buildings with at least one Room.
    The generator now covers the union — every Active building, prefilled where there
    are rooms to prefill — so delegating loses neither set.

    Kept as a name rather than deleted because it is the name the spec uses; it is no
    longer registered in ``hooks.py``, so the work runs once per day.

    """
    daily_cleaning_log_generator()
