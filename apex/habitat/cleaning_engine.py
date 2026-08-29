# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe.utils import cint, now_datetime

from apex.apex_core.utils.company import company_for_building


LEDGER_DOCTYPE = "Cleaning Compliance Ledger"
SOURCE_DOCTYPE = "Cleaning Log"


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
    doc.insert()
    return doc.name


def post_cleaning_compliance(doc) -> int:
    rows = doc.get("room_details") or []
    if not rows:
        return 0

    company = company_for_building(doc.building)
    assignee = getattr(doc, "cleaner_employee", None) or None

    posted = 0
    for row in rows:
        if frappe.db.exists(
            LEDGER_DOCTYPE,
            {"cleaning_log": doc.name, "source_detail_no": row.name, "is_cancelled": 0},
        ):
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
