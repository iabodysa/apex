# Copyright (c) 2026, afmcoltd

"""Masar personal service for a driver linked to an active Employee."""

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
    """Resolve Driver -> active linked Employee without accepting an employee id.

    Returns None when the driver has no active linked Employee — a configuration
    state, not a permission denial. Custody and housing hang off the Employee, so
    each caller with nothing to show for a None employee returns its own empty
    shape rather than raising.
    """
    driver = _resolve_driver()
    return frappe.db.get_value(
        "Salis Driver", {"name": driver, "status": "Active"}, "employee"
    )


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_masar_today():
    """Return only housed-bus execution state, excluding Salis fleet self-service."""
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
    """The session driver's own active accommodation assignment (read).

    An unlinked driver has no Employee to hang an assignment off, so this returns
    the same ``{}`` the ``/accommodation`` view already renders as its own no-data
    case — the DriverPage.vue fields view treats an empty dict as the empty state.
    """
    _require_enabled()
    employee = _resolve_linked_employee()
    if not employee:
        return {}
    return _active_assignment(employee) or {}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def get_my_custody():
    """The session driver's own live custody holding, scoped on ``employee`` —
    resolved from the portal identity via ``_resolve_linked_employee``, never a
    client-supplied id.

    An unlinked driver has no Employee to hold custody, so this returns the same
    ``{"items": []}`` the query below already returns when the Employee simply
    holds nothing — the collections view (``/custody``) renders that as empty."""
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
    """The session driver's own Resident Requests, scoped on ``employee`` —
    resolved from the portal identity via ``_resolve_linked_employee``, never a
    client-supplied id.

    An unlinked driver has no Employee to hold requests, so this returns the same
    ``[]`` the query below already returns when the Employee simply has none — the
    collections view (``/requests``) renders that as empty."""
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
