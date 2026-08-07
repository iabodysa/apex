# Copyright (c) 2026, afmcoltd

"""Cleaning compliance posting engine for the Habitat module.

Posts the immutable Cleaning Compliance Ledger from each Cleaning Log: one row
per Cleaning Log Room Detail child row, written on Cleaning Log submit and
reversed on cancel. Mirrors the no-GL, system-written ledger pattern of
``apex.salis.fuel_engine`` and
``apex.habitat.doctype.accommodation_stock_ledger``:

* in_create read-only DocType, posted only through ``_insert_ledger_row``;
* idempotency keyed on (cleaning_log, source_detail_no=child row name) so a
  re-run or a re-submit never double-posts;
* reverse-not-delete — a negative-fact mirror row with ``reversal_of`` set and
  both rows flagged ``is_cancelled`` — so the source nets out of every
  compliance sum while the original row is preserved for audit.

Reports read from this ledger so historical cleaning compliance is stable even
when the source Cleaning Log is later amended/cancelled.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, now_datetime

from apex.apex_core.utils.company import company_for_building

LEDGER_DOCTYPE = "Cleaning Compliance Ledger"
SOURCE_DOCTYPE = "Cleaning Log"


def _row_already_posted(cleaning_log: str, source_detail_no: str) -> bool:
    """Idempotency key: a live (non-cancelled) row already exists for this exact
    Cleaning Log child row."""
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "cleaning_log": cleaning_log,
                "source_detail_no": source_detail_no,
                "is_cancelled": 0,
            },
        )
    )


def _insert_ledger_row(
    *,
    company: str | None,
    posting_date,
    cleaning_log: str,
    building: str | None,
    room: str | None,
    cleaned: int,
    skip_reason: str | None,
    assignee: str | None,
    source_name: str,
    source_detail_no: str | None,
    reversal_of: str | None = None,
) -> str:
    """Insert one Cleaning Compliance Ledger row (system-written, no GL).

    ``source_doctype`` mirrors the originating "Cleaning Log"; ``source_name``
    points to the parent doc and ``source_detail_no`` to the child row name so a
    row is fully traceable back to the exact Room Detail it posted from.
    """
    doc = frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "company": company,
            "posting_date": posting_date,
            "cleaning_log": cleaning_log,
            "building": building,
            "room": room,
            "cleaned": cint(cleaned),
            "skip_reason": skip_reason,
            "assignee": assignee,
            "logged_at": now_datetime(),
            "source_doctype": SOURCE_DOCTYPE,
            "source_name": source_name,
            "source_detail_no": source_detail_no,
            "reversal_of": reversal_of,
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def post_cleaning_compliance(doc) -> int:
    """Post one immutable ledger row per Cleaning Log Room Detail child row.

    Fired from ``CleaningLog.on_submit``. Idempotent on (cleaning_log,
    source_detail_no): a child row already posted (live) is skipped, so a re-run
    or re-submit never double-posts. Returns the number of rows posted.

    The ``assignee`` is the internal cleaner Employee when known; the cleaned
    flag and skip reason come straight off the child row so the ledger captures
    per-room compliance, not just the parent's aggregate.
    """
    rows = doc.get("room_details") or []
    if not rows:
        return 0

    company = company_for_building(doc.building)
    assignee = getattr(doc, "cleaner_employee", None) or None

    posted = 0
    for row in rows:
        if _row_already_posted(doc.name, row.name):
            continue
        room_status = getattr(row, "room_status", None)
        cleaned = 0 if room_status == "Skipped" else cint(getattr(row, "cleaned", 0))
        _insert_ledger_row(
            company=company,
            posting_date=doc.cleaning_date,
            cleaning_log=doc.name,
            building=doc.building,
            room=row.room,
            cleaned=cleaned,
            skip_reason=getattr(row, "skip_reason", None),
            assignee=assignee,
            source_name=doc.name,
            source_detail_no=row.name,
        )
        posted += 1
    return posted


def reverse_cleaning_compliance(cleaning_log: str) -> int:
    """Reverse every live row posted from a cancelled/amended Cleaning Log.

    Fired from ``CleaningLog.on_cancel``. For each live original row (one whose
    ``reversal_of`` is unset and ``is_cancelled`` is 0) it posts a mirror row
    with ``cleaned`` zeroed and ``reversal_of`` set, then flags both the original
    and the mirror ``is_cancelled`` — so the Cleaning Log nets out of every
    compliance sum while both rows survive for audit. Mirrors the
    Accommodation Stock Ledger reversal idiom. Idempotent: only a live original
    is ever mirrored. Returns the number of reversal rows posted.
    """
    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "cleaning_log": cleaning_log,
            "reversal_of": ["is", "not set"],
            "is_cancelled": 0,
        },
        fields=[
            "name",
            "company",
            "posting_date",
            "building",
            "room",
            "skip_reason",
            "assignee",
            "source_name",
            "source_detail_no",
        ],
    )

    posted = 0
    for row in originals:
        rev = _insert_ledger_row(
            company=row.company,
            posting_date=row.posting_date,
            cleaning_log=cleaning_log,
            building=row.building,
            room=row.room,
            cleaned=0,
            skip_reason=row.skip_reason,
            assignee=row.assignee,
            source_name=row.source_name,
            source_detail_no=row.source_detail_no,
            reversal_of=row.name,
        )
        frappe.db.set_value(LEDGER_DOCTYPE, row.name, "is_cancelled", 1)
        frappe.db.set_value(LEDGER_DOCTYPE, rev, "is_cancelled", 1)
        posted += 1
    return posted
