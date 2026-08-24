# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import re

import frappe
from frappe import _

from frappe.utils import now_datetime, today

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.apex_core.utils.role_assignment import role_holders_escalating
from apex.apex_core.utils.system_notify import notify_user_system
from apex.habitat.tasks import backdate_assignment_cost

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
    if not tw.passport_number:
        return None
    return frappe.db.get_value(
        "Employee", {"passport_number": tw.passport_number, "status": "Active"}, "name"
    )

def repoint_party(tw_name: str, employee: str) -> None:
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
    repoint_party(tw.name, employee)

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
    frappe.db.set_value("Temporary Worker", tw.name, "status", "Expired")
    _notify_hr(
        _("Temporary Worker {0} ({1}) expired without an Employee link — the temporary window lapsed.").format(
            tw.name, tw.worker_name or tw.name
        )
    )

def _notify_hr(message: str) -> None:
    for user in role_holders_escalating("HR Manager", "System Manager"):
        notify_user_system(user, message)

