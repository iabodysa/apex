# Copyright (c) 2026, afmcoltd


import frappe

from apex.apex_core.utils.portal_identity import DRIVER, portal_room
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import _require_enabled, _resolve_driver
from apex.salis.api.driver_portal.trips import my_trips_today
from apex.salis.api.masar_worker import (
    _active_assignment,
    _custody_issued_by,
    _net_custody_items,
)


def _resolve_linked_employee():
    driver = _resolve_driver()
    return frappe.db.get_value(
        "Salis Driver", {"name": driver, "status": "Active"}, "employee"
    )


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_masar_today():
    _require_enabled()
    driver = _resolve_driver()
    employee = _resolve_linked_employee()
    return {
        "driver": driver,
        "employee": employee,
        "trips": my_trips_today(),
        "realtime_room": portal_room(DRIVER),
    }


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_my_accommodation():
    _require_enabled()
    employee = _resolve_linked_employee()
    if not employee:
        return {}
    return _active_assignment(employee) or {}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_my_custody():
    _require_enabled()
    employee = _resolve_linked_employee()
    if not employee:
        return {"items": []}
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "is_cancelled": 0,
            "item_type": "Custody Article",
            "employee": employee,
        },
        fields=[
            "building",
            "item",
            "item_name",
            "uom",
            "signed_qty",
            "posting_date",
            "voucher_type",
            "voucher_no",
        ],
        order_by="posting_date asc, creation asc",
    )
    items = _net_custody_items(rows)
    for item in items:
        item["issued_by"] = _custody_issued_by(
            item.pop("_issue_voucher"), item["building"]
        )
    items.sort(
        key=lambda row: (row["item_name"] or row["item"] or "", row["building"] or "")
    )
    return {"items": items}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_my_resident_requests():
    _require_enabled()
    employee = _resolve_linked_employee()
    if not employee:
        return []
    rows = frappe.get_all(
        "Resident Request",
        filters={"employee": employee},
        fields=[
            "name",
            "request_category",
            "priority",
            "issue_location",
            "description",
            "status",
            "resolution_notes",
            "creation",
        ],
        order_by="creation desc",
        limit=50,
    )
    for row in rows:
        row["creation"] = frappe.utils.cstr(row.get("creation"))
    return rows
