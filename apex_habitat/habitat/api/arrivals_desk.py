"""Arrivals Desk read API (MVP).

A read-only presentation layer for the unified "worker arrival" desk page. It
adds NO business logic of its own: every write the page performs goes through an
EXISTING whitelisted endpoint (Front Desk quick check-in, Custody Kiosk issue,
the Masar worker-link issuer, or a prefilled Transport Request new-doc form).

``get_arrival_card`` answers a single question for one employee — "where does
this worker stand on arrival?" — by reusing the same active-occupancy and
custody-presence semantics already used by the Front Desk board:

- current bed / project come from the single active Accommodation Assignment
  (``docstatus == 1`` AND ``check_out_date`` is not set);
- custody count is the worker's live custody balance read from the
  Accommodation Stock Ledger (employee-scoped Custody Article rows), the same
  ledger the Custody Issue controller posts to;
- the Masar token status reflects whether the worker already has an enabled
  personal link.

It is the source of truth for the page's done/pending chips. The page re-fetches
it after every write rather than mutating chips optimistically.
"""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def get_arrival_card(employee: str) -> dict:
    """Read-only arrival snapshot for one employee.

    Permission-gated on Employee read. Built from a bounded set of lookups (one
    Employee read, one active-assignment read, one custody-count, one token
    read) — no per-tile round trips beyond that.

    Args:
        employee: Employee docname (source of truth).

    Returns:
        dict shaped as ``{employee, employee_name, image, project,
        current_building, current_bed, current_bed_code, has_housing,
        custody_count, has_custody, masar_enabled, masar_status}``.
    """
    frappe.has_permission("Employee", "read", throw=True)

    emp = (
        frappe.db.get_value(
            "Employee", employee, ["employee_name", "image"], as_dict=True
        )
        or {}
    )
    if not emp:
        frappe.throw(_("Employee {0} does not exist.").format(employee))

    # Active accommodation assignment — same semantics as the Front Desk board
    # (docstatus == 1 AND check_out_date is not set).
    assignment = (
        frappe.db.get_value(
            "Accommodation Assignment",
            {"employee": employee, "docstatus": 1, "check_out_date": ["is", "not set"]},
            ["name", "project", "building", "bed"],
            as_dict=True,
        )
        or {}
    )

    current_bed = assignment.get("bed")
    current_bed_code = (
        frappe.db.get_value("Accommodation Bed", current_bed, "bed_code")
        if current_bed
        else None
    )

    # Live custody balance held by this worker — read from the Accommodation
    # Stock Ledger (the same ledger the Custody Issue controller posts to), via
    # ONE employee-scoped grouped pass over non-cancelled Custody Article rows.
    # custody_count = total signed qty the worker currently holds (issued minus
    # returned). No new business logic: the ledger is the existing source.
    ledger_rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={
            "item_type": "Custody Article",
            "employee": employee,
            "is_cancelled": 0,
        },
        fields=["qty"],
    )
    custody_count = int(sum(int(r.qty or 0) for r in ledger_rows))

    # Masar personal-link status — does the worker already have an enabled token?
    token = (
        frappe.db.get_value(
            "Masar Worker Token",
            {"employee": employee},
            ["token", "enabled"],
            as_dict=True,
        )
        or {}
    )
    masar_enabled = bool(token.get("token")) and bool(token.get("enabled"))

    return {
        "employee": employee,
        "employee_name": emp.get("employee_name"),
        "image": emp.get("image"),
        "project": assignment.get("project"),
        "current_building": assignment.get("building"),
        "current_bed": current_bed,
        "current_bed_code": current_bed_code,
        "has_housing": bool(current_bed),
        "custody_count": custody_count or 0,
        "has_custody": bool(custody_count),
        "masar_enabled": masar_enabled,
        "masar_status": "issued" if masar_enabled else "pending",
    }
