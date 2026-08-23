# Copyright (c) 2026, afmcoltd
"""Daily linking of Temporary Workers to real Employees (Batch 5 of the arrival redesign).

A worker arrives on a passport and is held on a Temporary Worker record. When HR later
registers him as a real Employee carrying the same passport number, this daily task
matches them, re-points the native ``party`` Dynamic Link from the Temporary Worker to
the Employee across every housing/custody doctype, back-dates the accommodation cost
that was skipped while he had no Employee, and marks the Temporary Worker ``Linked``. A
Temporary Worker whose window lapses without a match is marked ``Expired`` and HR is
notified.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.apex_core.utils.role_assignment import role_holders_escalating

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")

_ROW_SAVEPOINT = "temporary_worker_row"

_BATCH_SIZE = 500

PARTY_DOCTYPES = {
    "Housing Assignment": "employee",
    "Housing Checkout": "employee",
    "Room Bed Transfer": "employee",
    "Resident Request": "employee",
    "Idle Resident Report": "employee",
    "Accommodation Ledger": "employee",
    "Masar Worker Token": "employee",
    "Custody Issue": "issued_to_employee",
    "Custody Return": "returned_by_employee",
    "Custody Damage Assessment": "employee",
    "Accommodation Stock Ledger": "employee",
    "Custody Acknowledgment": "acknowledged_by_employee",
}

def link_temporary_workers() -> None:
    """Daily scheduler: link matured Temporary Workers to Employees; expire lapsed ones.

    Every Active worker is reached in one run, however many there are. The loop
    MUTATES the very field it filters on — ``_link`` flips status to Linked and
    ``_expire`` to Expired — so a processed row LEAVES the result set. Under the old
    offset cursor (``limit_start += page``) the rows behind it shifted down into the
    range the cursor had just passed and were skipped for the day, silently and with
    nothing logged. Paging on the last NAME seen fixes that: a key cannot shift, and
    ``name`` is immutable here (autoname is a naming series).

    ``fuel_engine``'s re-query-from-zero-and-exclude-failures idiom does not transfer:
    there a successful pass drains the filter, whereas a worker with no Employee yet
    legitimately STAYS Active, so its exclusion set would grow to the whole table.
    """
    from frappe.utils import today

    today_str = today()
    cursor = ""
    while True:
        workers = frappe.get_all(
            "Temporary Worker",
            filters={"status": "Active", "name": [">", cursor]},
            fields=["name", "passport_number", "worker_name", "expiry_date"],
            order_by="name asc",
            limit_page_length=_BATCH_SIZE,
        )
        if not workers:
            break
        for tw in workers:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                employee = _match_employee(tw)
                if employee:
                    _link(tw, employee)
                elif tw.expiry_date and str(tw.expiry_date) < today_str:
                    _expire(tw)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Temporary Worker link failed for {tw.name}"[:140],
                )
        cursor = workers[-1].name

def _match_employee(tw) -> str | None:
    """Find an active Employee carrying the same passport number, if any."""
    if not tw.passport_number:
        return None
    return frappe.db.get_value(
        "Employee", {"passport_number": tw.passport_number, "status": "Active"}, "name"
    )

def _repoint_party(tw_name: str, employee: str) -> None:
    """Re-point party_type/party (and the legacy Employee mirror) from the Temporary
    Worker to the Employee on every party-bearing doctype. Built with frappe.qb so
    the (dynamic) table and column identifiers are quoted by the builder, not
    string-interpolated: these include submitted documents, and this is a system
    identity correction, not a user edit.

    ``frappe.db.table_exists`` and ``get_table_columns``
    (frappe/database/database.py:1220) guard each target, because the party-bearing
    set spans modules that may not all be installed. The one thing a bulk UPDATE
    cannot do is skip a table it does not know about — it raises, and here that would
    abandon the identity correction half-applied across the tables before it."""
    for doctype, emp_field in PARTY_DOCTYPES.items():
        if not _IDENT.match(doctype):
            frappe.throw(_("Invalid SQL identifier: doctype {0}").format(doctype))
        if not _IDENT.match(emp_field):
            frappe.throw(_("Invalid SQL identifier: field {0}").format(emp_field))
        if not frappe.db.table_exists(doctype):
            continue
        if not {"party_type", "party", emp_field} <= set(frappe.db.get_table_columns(doctype)):
            continue
        tbl = frappe.qb.DocType(doctype)
        (
            frappe.qb.update(tbl)
            .set(tbl.party_type, PARTY_EMPLOYEE)
            .set(tbl.party, employee)
            .set(getattr(tbl, emp_field), employee)
            .where(tbl.party_type == PARTY_TEMPORARY_WORKER)
            .where(tbl.party == tw_name)
        ).run()

def _link(tw, employee: str) -> None:
    """Link a Temporary Worker to an Employee: re-point party across docs, back-date the
    skipped accommodation cost, then stamp the link and mark Linked.

    The cost back-dating is attempted inside its own try/except and its failure is
    logged through ``frappe.get_traceback`` (frappe/__init__.py) rather than raised: the identity link is
    the operator's request and it has already succeeded by then, so a costing fault
    must not undo it. The missed days remain recoverable by re-running the back-date.
    """
    from frappe.utils import now_datetime
    from apex.habitat.tasks import backdate_assignment_cost

    _repoint_party(tw.name, employee)

    for asg in frappe.get_all(
        "Housing Assignment",
        filters={"employee": employee, "docstatus": 1, "check_out_date": ["is", "not set"]},
        fields=["name", "check_in_date"],
    ):
        if asg.check_in_date:
            backdate_assignment_cost(asg.name, asg.check_in_date)

    frappe.db.set_value(
        "Temporary Worker",
        tw.name,
        {"linked_employee": employee, "linked_on": now_datetime(), "status": "Linked"},
    )
    try:
        frappe.get_doc("Temporary Worker", tw.name).add_comment(
            "Comment",
            _("Linked to Employee {0} (passport match); housing/custody re-pointed and cost back-dated.").format(
                employee
            ),
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Temporary Worker link: comment failed")

def _expire(tw) -> None:
    """Mark a lapsed Temporary Worker Expired and notify HR."""
    frappe.db.set_value("Temporary Worker", tw.name, "status", "Expired")
    _notify_hr(
        _("Temporary Worker {0} ({1}) expired without an Employee link — the temporary window lapsed.").format(
            tw.name, tw.worker_name or tw.name
        )
    )

def _notify_hr(message: str) -> None:
    """Post an in-app Notification Log to HR Manager users (fallback System Manager).

    Per-user delivery via the shared system_notify helper (the single Notification
    Log writer); the subject IS the message here.
    """
    from apex.apex_core.utils.system_notify import notify_user_system

    for user in role_holders_escalating("HR Manager", "System Manager"):
        notify_user_system(user, message)

