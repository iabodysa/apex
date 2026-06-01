"""Arrivals Desk read + lookup API (party-aware).

A presentation/lookup layer for the unified worker-arrival desk page. The page's
WRITES go through existing whitelisted endpoints (the party-aware Front Desk
quick_check_in, the Custody Kiosk issue, the Masar worker-link issuer). This
module adds:

- ``get_arrival_card`` — the party-aware arrival snapshot (Employee | Temporary
  Worker), built from the same active-occupancy / custody / token semantics as the
  Front Desk board. ``employee=`` is kept as a legacy alias for an Employee party,
  and the legacy ``employee``/``employee_name`` keys stay in the response, so the
  old desk keeps working.
- ``search_arrivals_workers`` — one combined search returning registered Employees
  first, then active Temporary Workers, each tagged with its ``party_type``.
- ``register_temporary_worker`` — register a passport-only new arrival. A housing
  supervisor may create a Temporary Worker but NEVER an Employee (the doctype is
  hard-coded; Employee creation is HRMS-gated and unreachable here).
"""

from __future__ import annotations

import frappe
from frappe import _

PARTY_EMPLOYEE = "Employee"
PARTY_TEMPORARY_WORKER = "Temporary Worker"


@frappe.whitelist()
def get_arrival_card(party_type=None, party=None, employee=None) -> dict:
    """Party-aware arrival snapshot for one worker (Employee or Temporary Worker)."""
    # Legacy alias: a bare `employee` means an Employee party (back-compat).
    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    if not (party_type and party):
        frappe.throw(_("party_type and party are required."))

    if party_type == PARTY_EMPLOYEE:
        frappe.has_permission("Employee", "read", throw=True)
        info = frappe.db.get_value("Employee", party, ["employee_name", "image"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Employee {0} does not exist.").format(party))
        worker_name, image = info.get("employee_name"), info.get("image")
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        info = frappe.db.get_value("Temporary Worker", party, ["worker_name"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Temporary Worker {0} does not exist.").format(party))
        worker_name, image = info.get("worker_name"), None
    else:
        frappe.throw(_("Unknown party type: {0}").format(party_type))

    # Active accommodation assignment — same semantics as the Front Desk board,
    # now keyed on the native party instead of employee.
    assignment = (
        frappe.db.get_value(
            "Accommodation Assignment",
            {"party_type": party_type, "party": party, "docstatus": 1, "check_out_date": ["is", "not set"]},
            ["name", "project", "building", "bed"],
            as_dict=True,
        )
        or {}
    )
    current_bed = assignment.get("bed")
    current_bed_code = (
        frappe.db.get_value("Accommodation Bed", current_bed, "bed_code") if current_bed else None
    )

    # Custody balance comes from the (Employee-scoped) Accommodation Stock Ledger.
    # A Temporary Worker's custody stock is DEFERRED by design (no posting until he
    # is linked to an Employee), so his ledger balance reads 0 here — correct.
    custody_count = 0
    if party_type == PARTY_EMPLOYEE:
        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"item_type": "Custody Article", "employee": party, "is_cancelled": 0},
            fields=["qty"],
        )
        custody_count = int(sum(int(r.qty or 0) for r in rows))

    token = (
        frappe.db.get_value(
            "Masar Worker Token", {"party_type": party_type, "party": party}, ["token", "enabled"], as_dict=True
        )
        or {}
    )
    masar_enabled = bool(token.get("token")) and bool(token.get("enabled"))

    return {
        "party_type": party_type,
        "party": party,
        "employee": party if party_type == PARTY_EMPLOYEE else None,  # legacy key
        "employee_name": worker_name,  # legacy key
        "worker_name": worker_name,
        "image": image,
        "project": assignment.get("project"),
        "current_building": assignment.get("building"),
        "current_bed": current_bed,
        "current_bed_code": current_bed_code,
        "has_housing": bool(current_bed),
        "custody_count": custody_count,
        "has_custody": bool(custody_count),
        "masar_enabled": masar_enabled,
        "masar_status": "issued" if masar_enabled else "pending",
    }


@frappe.whitelist()
def search_arrivals_workers(building=None, txt=None) -> list:
    """Combined worker lookup for the desk: registered Employees first, then active
    Temporary Workers, each tagged with ``party_type`` so the page can house either.
    Read-permission-gated per doctype (a user who cannot read a doctype gets none)."""
    txt = (txt or "").strip()
    results = []

    if frappe.has_permission("Employee", "read"):
        emps = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            or_filters=(
                [["employee_name", "like", f"%{txt}%"], ["name", "like", f"%{txt}%"]] if txt else None
            ),
            fields=["name", "employee_name", "designation"],
            order_by="employee_name asc",
            limit_page_length=15,
        )
        results += [
            {
                "party_type": PARTY_EMPLOYEE,
                "party": e.name,
                "label": e.employee_name or e.name,
                "sub": e.designation or e.name,
            }
            for e in emps
        ]

    if frappe.has_permission("Temporary Worker", "read"):
        tws = frappe.get_all(
            "Temporary Worker",
            filters={"status": "Active"},
            or_filters=(
                [
                    ["worker_name", "like", f"%{txt}%"],
                    ["passport_number", "like", f"%{txt}%"],
                    ["name", "like", f"%{txt}%"],
                ]
                if txt
                else None
            ),
            fields=["name", "worker_name", "passport_number"],
            order_by="modified desc",
            limit_page_length=15,
        )
        results += [
            {
                "party_type": PARTY_TEMPORARY_WORKER,
                "party": t.name,
                "label": t.worker_name or t.name,
                "sub": _("Passport {0}").format(t.passport_number or "—"),
            }
            for t in tws
        ]

    return results


@frappe.whitelist(methods=["POST"])
def register_temporary_worker(
    worker_name,
    passport_number,
    nationality=None,
    labour_supplier=None,
    building=None,
    project=None,
    cell_number=None,
    iqama_number=None,
) -> dict:
    """Register a passport-only new arrival as a Temporary Worker, returned pre-selected
    for housing. A housing supervisor may create a Temporary Worker but NEVER an
    Employee — the doctype is hard-coded and Employee creation is HRMS-gated.
    The Temporary Worker controller enforces its own rules (unique passport, the
    30/90-day window, expiry computation)."""
    frappe.has_permission("Temporary Worker", "create", throw=True)
    doc = frappe.get_doc(
        {
            "doctype": "Temporary Worker",
            "worker_name": worker_name,
            "passport_number": passport_number,
            "nationality": nationality,
            "labour_supplier": labour_supplier,
            "building": building,
            "project": project,
            "cell_number": cell_number,
            "iqama_number": iqama_number,
        }
    )
    doc.insert()
    return {
        "party_type": PARTY_TEMPORARY_WORKER,
        "party": doc.name,
        "label": doc.worker_name,
        "expiry_date": doc.expiry_date,
    }


@frappe.whitelist(methods=["POST"])
def house_over_capacity(room, party_type, party, project, check_in_date=None) -> dict:
    """House a worker beyond a full room's physical capacity by minting a TEMPORARY
    (virtual, ``is_temporary``) Accommodation Bed in the room and assigning to it.

    The building's over-capacity headroom is enforced by Accommodation
    Assignment.validate (building-level projected occupancy vs ``total_capacity``
    and ``over_capacity_allowed``). quick_check_in performs no intermediate commit,
    so when that gate rejects the assignment the whole request — including the
    just-minted bed — rolls back. ``total_capacity`` is a stored building field and
    is NOT inflated by the temporary bed, so the cap is measured against true
    capacity. Each worker still gets his own bed, so the assignment bed-lock and
    occupancy controllers are untouched.
    """
    from apex_habitat.habitat.api.front_desk import quick_check_in

    frappe.has_permission("Accommodation Bed", "create", throw=True)
    if not frappe.db.exists("Accommodation Room", room):
        frappe.throw(_("Room {0} does not exist.").format(room))

    n = frappe.db.count("Accommodation Bed", {"room": room, "is_temporary": 1}) + 1
    bed = frappe.get_doc(
        {
            "doctype": "Accommodation Bed",
            "room": room,
            "bed_code": f"{room}-OC{n}",
            "status": "Available",
            "is_temporary": 1,
        }
    )
    bed.insert()

    result = quick_check_in(
        bed=bed.name,
        party_type=party_type,
        party=party,
        project=project,
        check_in_date=check_in_date,
    )
    return {**result, "is_temporary": True, "bed_code": bed.bed_code}
