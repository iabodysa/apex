# Copyright (c) 2026, afmcoltd

"""Facility asset movement ledger engine.

Records each facility-asset relocation as an immutable Facility Asset Movement
Ledger row, mirroring the Habitat no-GL system-written ledger pattern
(``accommodation_ledger``) and the idempotent reverse-not-delete idiom in
``salis.fuel_engine``.

Both writes pass ``ignore_permissions``, and that is the ledger idiom rather than a shortcut: the
row is posted from the movement document's submit and cancel, where the operator's permission was
already checked. A DocPerm granting operators insert here would let them write movement rows with
no movement behind them, which an immutable subledger must refuse.

The Facility Asset Movement controller already updates the asset's location
in place (``building``/``location_in_building``) on submit, which leaves no
history. This engine is additive: it posts one ledger row per submitted
movement capturing from->to, so the relocation history is queryable, and posts
a negated reversal row on cancel instead of editing or deleting the original.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate


LEDGER_DOCTYPE = "Facility Asset Movement Ledger"


def ensure_asset_still_at(facility_asset: str, **expected) -> None:
    """Refuse to cancel a relocation record the asset has already moved on from.

    A Facility Asset carries ONE mutable location, so restoring a cancelled
    record's origin while a LATER relocation is still submitted would silently
    discard that later move and leave the asset contradicting its own ledger. The
    honest remedy is last-in-first-out: cancel the newest relocation first.

    ``expected`` maps Facility Asset location fieldnames to the values this record
    wrote when it moved the asset; only the fields passed are compared, because
    the delivery path leaves the room untouched when it carries no destination
    room of its own.
    """
    fields = list(dict.fromkeys(["building", *expected]))
    current = frappe.db.get_value("Facility Asset", facility_asset, fields, as_dict=True)
    if not current:
        return
    if all((current.get(field) or None) == (value or None) for field, value in expected.items()):
        return
    frappe.throw(
        _(
            "Facility Asset {0} has moved on to {1} since this record; cancelling it now"
            " would undo a later relocation. Cancel the newest relocation first."
        ).format(facility_asset, current.building)
    )


def ledgered_origin(source_doctype: str, source_name: str):
    """Where this source took the asset FROM, as it ledgered the move — or None if
    it never posted a row.

    A Facility Asset Delivery has no origin-room field of its own (only
    ``to_location_in_building``), so its ledger row is the one place the room the
    asset actually left survives. Cancel reads it back to return the asset to that
    room instead of leaving it parked in the destination's.
    """
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "source_doctype": source_doctype,
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        fields=["from_building", "from_location"],
        limit=1,
    )
    return rows[0] if rows else None


def _latest_surviving_movement(facility_asset: str):
    """The newest original ledger row for the asset that no reversal points at —
    i.e. the asset's most recent move that still stands. None once every move it
    ever made has been cancelled."""
    reversed_originals = set(
        frappe.get_all(
            LEDGER_DOCTYPE,
            filters={"facility_asset": facility_asset, "reversal_of": ["is", "set"]},
            pluck="reversal_of",
        )
    )
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={"facility_asset": facility_asset, "reversal_of": ["is", "not set"]},
        fields=["name", "posting_datetime", "from_building", "from_location"],
        order_by="posting_datetime desc, creation desc",
    )
    for row in rows:
        if row.name not in reversed_originals:
            return row
    return None


def restore_asset_audit_trail(facility_asset: str) -> None:
    """Re-derive the asset's movement audit trail from the history a cancel left
    standing.

    ``previous_building``, ``previous_location_in_building`` and
    ``last_movement_date`` are snapshots taken on SUBMIT. A cancel that restores
    the location but leaves those three behind has the asset citing a movement
    that no longer exists: reverting one move on a fresh asset read "at A,
    previously A", still stamped with the cancelled move's date.

    The ledger is the movement history, so the honest values are the newest
    surviving row's origin and posting date — or blank when the cancel undid the
    asset's only move, which is exactly what a never-moved asset reads.

    Call AFTER ``reverse_asset_movement``, so the row being cancelled is already
    excluded from the history.
    """
    latest = _latest_surviving_movement(facility_asset)
    frappe.db.set_value(
        "Facility Asset",
        facility_asset,
        {
            "previous_building": latest.from_building if latest else None,
            "previous_location_in_building": latest.from_location if latest else None,
            "last_movement_date": getdate(latest.posting_datetime) if latest else None,
        },
    )


def _ledger_exists(source_doctype: str, source_name: str) -> bool:
    """True if an original ledger row already exists for this source (idempotency
    key = source + not-a-reversal), so a re-submit cannot double-post."""
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "source_doctype": source_doctype,
                "source_name": source_name,
                "reversal_of": ["is", "not set"],
            },
        )
    )


def _insert_ledger_row(
    facility_asset: str,
    company: str | None,
    posting_date,
    from_building: str | None,
    from_location: str | None,
    to_building: str | None,
    to_location: str | None,
    moved_by: str | None,
    source_doctype: str,
    source_name: str,
) -> None:
    """Insert one Facility Asset Movement Ledger row (system-written, no GL).

    Idempotent on ``(source_doctype, source_name)`` for original rows: a source
    already ledgered is skipped.
    """
    if _ledger_exists(source_doctype, source_name):
        return
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "facility_asset": facility_asset,
            "company": company,
            "posting_datetime": posting_date,
            "from_building": from_building,
            "from_location": from_location,
            "to_building": to_building,
            "to_location": to_location,
            "moved_by_user": moved_by,
            "source_doctype": source_doctype,
            "source_name": source_name,
        }
    ).insert(ignore_permissions=True)


def post_asset_movement(doc) -> None:
    """Post the immutable from->to ledger row for a submitted Facility Asset
    Movement. ``moved_by`` on the source is an Employee link; the ledger records
    the acting User instead, so map it to the current session user."""
    from frappe.utils import now_datetime

    _insert_ledger_row(
        facility_asset=doc.facility_asset,
        company=doc.from_company or doc.to_company,
        posting_date=now_datetime(),
        from_building=doc.from_building,
        from_location=doc.from_room,
        to_building=doc.to_building,
        to_location=doc.to_room,
        moved_by=frappe.session.user,
        source_doctype=doc.doctype,
        source_name=doc.name,
    )


def reverse_asset_movement(source_doctype: str, source_name: str) -> int:
    """Reverse the ledgered movement for a cancelled Facility Asset Movement.

    Posts a mirror row for each original ledger row of that source with from/to
    swapped and ``is_cancelled`` set, linked back via ``reversal_of`` — the
    Accommodation Ledger / fuel-engine reversal idiom (negate, don't delete). The
    original row is preserved for audit.

    Idempotent: an original that already has a reversal pointing at it is skipped,
    so calling it twice posts at most one reversal per original. Returns the
    number of reversal rows posted.
    """
    from frappe.utils import now_datetime

    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "source_doctype": source_doctype,
            "source_name": source_name,
            "reversal_of": ["is", "not set"],
        },
        fields=[
            "name",
            "facility_asset",
            "company",
            "from_building",
            "from_location",
            "to_building",
            "to_location",
            "moved_by_user",
        ],
    )

    posted = 0
    for row in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": row.name}):
            continue
        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "facility_asset": row.facility_asset,
                "company": row.company,
                "posting_datetime": now_datetime(),
                "from_building": row.to_building,
                "from_location": row.to_location,
                "to_building": row.from_building,
                "to_location": row.from_location,
                "moved_by_user": row.moved_by_user,
                "is_cancelled": 1,
                "source_doctype": source_doctype,
                "source_name": source_name,
                "reversal_of": row.name,
            }
        ).insert(ignore_permissions=True)
        posted += 1

    return posted
