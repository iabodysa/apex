# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

# [#evsc2k]
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

    # [#exgi8j]
    already = {
        r["building"]
        for r in frappe.get_all(
            "Cleaning Log",
            filters={"cleaning_date": cleaning_date, "docstatus": ["!=", 2]},
            fields=["building"],
        )
        if r["building"]
    }

    # [#qqq6iv]
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
            if not rooms:
                # [#p9768y]
                continue

            # [#k5xrmx]
            frappe.db.savepoint(_CLEANING_SAVEPOINT)
            try:
                log = frappe.get_doc({
                    "doctype": "Cleaning Log",
                    "building": building,
                    "cleaning_date": cleaning_date,
                    # [#thdaxn]
                    "room_details": [{"room": room} for room in rooms],
                })
                log.insert(ignore_permissions=True)  # audit-ok — scheduler-run daily cleaning record, no user session
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
    """Scheduled daily — create one draft Cleaning Log per active building that
    has a Housing Supervisor assigned, skipping buildings already logged today.

    This is the T-554 spec-named entry point. The heavier variant that also
    pre-populates room_details rows is ``daily_cleaning_log_generator``
    (registered separately). This function targets buildings that have an
    assigned ``responsible_supervisor`` and creates a minimal log so
    the supervisor finds a ready record each morning.

    Guard: ``frappe.db.exists("Cleaning Log", {"building": bld, "cleaning_date":
    today()})`` — one log per (building, cleaning_date), non-cancelled.
    """
    from frappe.utils import today

    cleaning_date = today()
    logger = frappe.logger()

    # [#hsr1dx]
    buildings = frappe.get_all(
        "Building",
        filters={
            "status": "Active",
            "responsible_supervisor": ["is", "set"],
        },
        fields=["name", "responsible_supervisor"],
    )

    created = 0
    for bld in buildings:
        if frappe.db.exists(
            "Cleaning Log",
            {"building": bld.name, "cleaning_date": cleaning_date, "docstatus": ["!=", 2]},
        ):
            continue

        # [#burq2n]
        frappe.db.savepoint(_CLEANING_SAVEPOINT)
        try:
            log = frappe.get_doc({
                "doctype": "Cleaning Log",
                "building": bld.name,
                "cleaning_date": cleaning_date,
            })
            log.insert(ignore_permissions=True)  # audit-ok — scheduler-run daily cleaning record
        except Exception:
            frappe.db.rollback(save_point=_CLEANING_SAVEPOINT)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"auto_create_cleaning_logs: insert failed for {bld.name}"[:140],
            )
        else:
            frappe.db.release_savepoint(_CLEANING_SAVEPOINT)
            created += 1

    logger.info(f"auto_create_cleaning_logs: created {created} cleaning log(s) for {cleaning_date}.")
