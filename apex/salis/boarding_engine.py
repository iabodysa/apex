# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import today

from apex.apex_core.utils.company import company_for_trip
from apex.apex_core.utils.portal_identity import DRIVER, as_capacity
from apex.salis.api.boarding_flow import _assigned_request_names, _request_workers


LEDGER_DOCTYPE = "Trip Boarding Ledger"

TERMINAL_OUTCOMES = ("Boarded", "Absent")


def _worker_buildings(dispatch_trip: str) -> dict[str, str]:
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


def post_trip_boarding(dispatch_trip: str) -> int:
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

    with as_capacity(DRIVER, trip.driver):
        for row in rows:
            if row.status not in TERMINAL_OUTCOMES or not row.employee:
                continue
            sp = "boarding_row"
            frappe.db.savepoint(sp)
            try:
                if frappe.db.exists(
                    LEDGER_DOCTYPE,
                    {
                        "dispatch_trip": dispatch_trip,
                        "employee": row.employee,
                        "reversal_of": ["is", "not set"],
                    },
                ):
                    continue
                boarded_at = (
                    row.worker_claim_at if row.status == "Boarded" else None
                )
                frappe.get_doc(
                    {
                        "doctype": LEDGER_DOCTYPE,
                        "company": company,
                        "posting_date": posting_date,
                        "dispatch_trip": dispatch_trip,
                        "employee": row.employee,
                        "building": buildings.get(row.employee),
                        "outcome": row.status,
                        "confirm_source": row.confirm_source or None,
                        "boarded_at": boarded_at,
                        "source_doctype": "Dispatch Trip",
                        "source_name": dispatch_trip,
                        "source_detail_no": row.employee,
                    }
                ).insert()
                posted += 1
            except Exception:
                frappe.db.rollback(save_point=sp)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Trip boarding post failed for {dispatch_trip}/{row.employee}"[:140],
                )

    return posted


def reverse_trip_boarding(dispatch_trip: str) -> int:
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
        ).insert()
        frappe.db.set_value(
            LEDGER_DOCTYPE, row.name, "is_cancelled", 1, update_modified=False
        )
        posted += 1

    return posted
