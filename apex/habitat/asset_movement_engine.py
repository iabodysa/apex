# Copyright (c) 2026, AFMCO and contributors

"""Facility asset movement ledger engine.

Records each facility-asset relocation as an immutable Facility Asset Movement
Ledger row, mirroring the Habitat no-GL system-written ledger pattern
(``accommodation_ledger``) and the idempotent reverse-not-delete idiom in
``salis.fuel_engine``.

The Facility Asset Movement controller already updates the asset's location
in place (``building``/``location_in_building``) on submit, which leaves no
history. This engine is additive: it posts one ledger row per submitted
movement capturing from->to, so the relocation history is queryable, and posts
a negated reversal row on cancel instead of editing or deleting the original.
"""

from __future__ import annotations

import frappe

LEDGER_DOCTYPE = "Facility Asset Movement Ledger"


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
    ).insert(ignore_permissions=True)  # audit-ok


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
                # [#7b7rjz]
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
        ).insert(ignore_permissions=True)  # audit-ok
        posted += 1

    return posted
