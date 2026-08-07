# Copyright (c) 2026, afmcoltd
"""Boarding ledger engine for the Salis Movement module.

Posting engine that mirrors the immutable, source-traceable ledger idiom of
``fuel_engine`` / ``rental_engine`` and the Trip Fulfilment Ledger: it turns each
worker's FINAL boarding outcome — held only in the mutable ``Trip Boarding State``
child on Dispatch Trip (operational, retroactively editable) — into one immutable
Trip Boarding Ledger row, so per-worker boarding reports stay stable when that
child is later edited.

Two entry points, both idempotent and ignore_permissions (the ledger grants no
human write role):

* ``post_trip_boarding(dispatch_trip)`` — called from the finalize path
  (``boarding_flow.depart_and_finalize``) once the Boarded/Absent outcomes have
  settled. Posts one row per Trip Boarding State worker with a TERMINAL outcome
  (Boarded or Absent). Idempotent on ``(dispatch_trip, employee)`` for original
  (non-reversal) rows, so re-running posts no duplicate.
* ``reverse_trip_boarding(dispatch_trip)`` — reverse-not-delete on trip cancel:
  for each original posted row, post a mirror reversal row (``is_cancelled=1`` +
  ``reversal_of`` pointing at the original) and flag the original ``is_cancelled``,
  so the outcome nets out of every report while the original is preserved for
  audit. Idempotent: a row already reversed is skipped.

No GL, no money — a categorical operational memo only.
"""

from __future__ import annotations

import frappe
from frappe.utils import today

from apex.apex_core.utils.company import company_for_trip

LEDGER_DOCTYPE = "Trip Boarding Ledger"

TERMINAL_OUTCOMES = ("Boarded", "Absent")


def _ledger_exists(dispatch_trip: str, employee: str) -> bool:
    """True if an ORIGINAL ledger row already exists for this trip+worker
    (idempotency key). A reversal row is excluded so re-posting after a reversal
    is still guarded by the original it mirrors, not by the mirror."""
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "dispatch_trip": dispatch_trip,
                "employee": employee,
                "reversal_of": ["is", "not set"],
            },
        )
    )


def _worker_buildings(dispatch_trip: str) -> dict[str, str]:
    """Map each manifest worker -> the Accommodation Building of the Transport
    Request they belong to (their housing pickup). The trip manifest is the union
    of the Route Plan request and every assigned request; a worker's building is
    the building of the FIRST request that lists them. Best-available per-worker
    snapshot — the boarding state child carries no building of its own."""
    from apex.salis.api.boarding_flow import (
        _assigned_request_names,
        _request_workers,
    )

    transport_request = frappe.db.get_value(
        "Dispatch Trip", dispatch_trip, "transport_request"
    )
    mapping: dict[str, str] = {}
    for request in [transport_request, *_assigned_request_names(dispatch_trip)]:
        if not request:
            continue
        building = frappe.db.get_value(
            "Transport Request", request, "accommodation_building"
        )
        if not building:
            continue
        for employee in _request_workers(request):
            if employee and employee not in mapping:
                mapping[employee] = building
    return mapping


def _insert_ledger_row(
    dispatch_trip: str,
    employee: str,
    building: str | None,
    outcome: str,
    confirm_source: str | None,
    boarded_at,
    company: str | None,
    posting_date: str,
) -> None:
    """Insert one Trip Boarding Ledger row (system-written, no GL).

    Source traceability: the originating record is the Dispatch Trip, and the
    worker id is stamped into ``source_detail_no`` so the row points back to the
    exact Trip Boarding State child it snapshots."""
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "company": company,
            "posting_date": posting_date,
            "dispatch_trip": dispatch_trip,
            "employee": employee,
            "building": building,
            "outcome": outcome,
            "confirm_source": confirm_source,
            "boarded_at": boarded_at,
            "source_doctype": "Dispatch Trip",
            "source_name": dispatch_trip,
            "source_detail_no": employee,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def post_trip_boarding(dispatch_trip: str) -> int:
    """Post one immutable Trip Boarding Ledger row per terminal-outcome worker.

    Reads the trip's Trip Boarding State child and, for every row whose status is
    a terminal outcome (Boarded / Absent), inserts a ledger row capturing that
    final outcome. Workers still in a non-terminal state (Pending / Worker Claimed
    / Driver Rejected) are NOT posted — they have no settled outcome yet.

    Idempotent on ``(dispatch_trip, employee)``: a worker already posted (original
    row) is skipped, so calling it again after a re-finalize posts no duplicate.
    Per-row savepoint isolates a failing row; no commit inside the loop. Returns
    the number of rows posted.
    """
    if not dispatch_trip:
        return 0

    trip = frappe.get_doc("Dispatch Trip", dispatch_trip)
    rows = trip.boarding_state or []
    if not rows:
        return 0

    company = company_for_trip(dispatch_trip)
    buildings = _worker_buildings(dispatch_trip)
    posting_date = today()
    posted = 0

    for row in rows:
        if row.status not in TERMINAL_OUTCOMES or not row.employee:
            continue
        sp = "boarding_row"
        frappe.db.savepoint(sp)
        try:
            if _ledger_exists(dispatch_trip, row.employee):
                continue
            boarded_at = (
                row.worker_claim_at if row.status == "Boarded" else None
            )
            _insert_ledger_row(
                dispatch_trip=dispatch_trip,
                employee=row.employee,
                building=buildings.get(row.employee),
                outcome=row.status,
                confirm_source=row.confirm_source or None,
                boarded_at=boarded_at,
                company=company,
                posting_date=posting_date,
            )
            posted += 1
        except Exception:
            frappe.db.rollback(save_point=sp)
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Trip boarding post failed for {dispatch_trip}/{row.employee}"[:140],
            )

    return posted


def reverse_trip_boarding(dispatch_trip: str) -> int:
    """Reverse-not-delete the posted boarding rows for a cancelled trip.

    For each ORIGINAL Trip Boarding Ledger row of the trip (``reversal_of`` unset,
    not yet cancelled), post a mirror reversal row carrying the same identity,
    ``is_cancelled=1`` and ``reversal_of`` set to the original, then flag the
    original ``is_cancelled=1`` via frappe.db.set_value (a direct DB write — the
    controller blocks every ORM re-save). The outcome then nets out of every
    report while the original is preserved for audit.

    Mirrors the fuel/rental reversal idiom (negative mirror + ``reversal_of``),
    adapted to a categorical outcome via the ``is_cancelled`` flag. Idempotent:
    an original that already has a reversal is skipped. Returns the number of
    reversal rows posted (0 if the trip was never posted or is already reversed).
    """
    if not dispatch_trip:
        return 0

    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "dispatch_trip": dispatch_trip,
            "reversal_of": ["is", "not set"],
        },
        fields=[
            "name",
            "company",
            "posting_date",
            "employee",
            "building",
            "outcome",
            "confirm_source",
            "boarded_at",
        ],
    )

    posted = 0
    for row in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": row.name}):
            continue
        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "company": row.company,
                "posting_date": today(),
                "dispatch_trip": dispatch_trip,
                "employee": row.employee,
                "building": row.building,
                "outcome": row.outcome,
                "confirm_source": row.confirm_source,
                "boarded_at": row.boarded_at,
                "source_doctype": "Dispatch Trip",
                "source_name": dispatch_trip,
                "source_detail_no": row.employee,
                "is_cancelled": 1,
                "reversal_of": row.name,
            }
        ).insert(ignore_permissions=True)  # audit-ok
        frappe.db.set_value(
            LEDGER_DOCTYPE, row.name, "is_cancelled", 1, update_modified=False
        )
        posted += 1

    return posted
