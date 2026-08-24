# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


LEDGER_DOCTYPE = "Facility Asset Movement Ledger"


def ensure_asset_still_at(facility_asset: str, **expected) -> None:
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


def post_asset_movement(doc) -> None:
    if frappe.db.exists(
        LEDGER_DOCTYPE,
        {
            "source_doctype": doc.doctype,
            "source_name": doc.name,
            "reversal_of": ["is", "not set"],
        },
    ):
        return
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "facility_asset": doc.facility_asset,
            "company": doc.from_company or doc.to_company,
            "posting_datetime": now_datetime(),
            "from_building": doc.from_building,
            "from_location": doc.from_room,
            "to_building": doc.to_building,
            "to_location": doc.to_room,
            "moved_by_user": frappe.session.user,
            "source_doctype": doc.doctype,
            "source_name": doc.name,
        }
    ).insert(ignore_permissions=True)


def reverse_asset_movement(source_doctype: str, source_name: str) -> int:
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
