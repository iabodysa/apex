# Copyright (c) 2026, AFMCO and contributors
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

from apex_habitat.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER

# [#tutwiu]
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")

# [#g9r6ee]
PARTY_DOCTYPES = {
    "Accommodation Assignment": "employee",
    "Accommodation Checkout": "employee",
    "Room Bed Transfer": "employee",
    "Accommodation Resident Request": "employee",
    "Idle Resident Report": "employee",
    "Accommodation Ledger": "employee",
    "Masar Worker Token": "employee",
    "Custody Issue": "issued_to_employee",
    "Custody Return": "returned_by_employee",
    "Custody Damage Assessment": "employee",
}


def link_temporary_workers() -> None:
    """Daily scheduler: link matured Temporary Workers to Employees; expire lapsed ones."""
    from frappe.utils import today

    today_str = today()
    start = 0
    batch_size = 500
    while True:
        workers = frappe.get_all(
            "Temporary Worker",
            filters={"status": "Active"},
            fields=["name", "passport_number", "worker_name", "expiry_date"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not workers:
            break
        for tw in workers:
            try:  # [#s7axbr]
                employee = _match_employee(tw)
                if employee:
                    _link(tw, employee)
                elif tw.expiry_date and str(tw.expiry_date) < today_str:
                    _expire(tw)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Temporary Worker link failed for {tw.name}"[:140],
                )
        start += batch_size


def _match_employee(tw) -> str | None:
    """Find an active Employee carrying the same passport number, if any."""
    if not tw.passport_number:
        return None
    return frappe.db.get_value(
        "Employee", {"passport_number": tw.passport_number, "status": "Active"}, "name"
    )


def _repoint_party(tw_name: str, employee: str) -> None:
    """Re-point party_type/party (and the legacy Employee mirror) from the Temporary
    Worker to the Employee on every party-bearing doctype. Direct, parameterised SQL:
    these include submitted documents, and this is a system identity correction, not a
    user edit. Existence-guarded on table + columns."""
    for doctype, emp_field in PARTY_DOCTYPES.items():
        if not _IDENT.match(doctype):
            frappe.throw(_("Invalid SQL identifier: doctype {0}").format(doctype))
        if not _IDENT.match(emp_field):
            frappe.throw(_("Invalid SQL identifier: field {0}").format(emp_field))
        if not frappe.db.table_exists(doctype):
            continue
        if not {"party_type", "party", emp_field} <= set(frappe.db.get_table_columns(doctype)):
            continue
        frappe.db.sql(
            f"""
            UPDATE `tab{doctype}`
            SET party_type = %(emp_type)s, party = %(emp)s, `{emp_field}` = %(emp)s
            WHERE party_type = %(tw_type)s AND party = %(tw)s
            """,
            {
                "emp_type": PARTY_EMPLOYEE,
                "emp": employee,
                "tw_type": PARTY_TEMPORARY_WORKER,
                "tw": tw_name,
            },
        )


def _link(tw, employee: str) -> None:
    """Link a Temporary Worker to an Employee: re-point party across docs, back-date the
    skipped accommodation cost, then stamp the link and mark Linked."""
    from frappe.utils import now_datetime
    # [#1ouyds]
    from apex_habitat.habitat.tasks import backdate_assignment_cost

    _repoint_party(tw.name, employee)

    # [#28clra]
    for asg in frappe.get_all(
        "Accommodation Assignment",
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
        # [#l55n57]
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
    """Post an in-app Notification Log to HR Manager users (fallback System Manager)."""
    try:
        for user in _hr_recipients():
            frappe.get_doc({
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",
                "subject": message[:140],
                "email_content": message,
            }).insert(ignore_permissions=True)  # audit-ok — system HR alert
    except Exception:
        frappe.db.rollback()
        frappe.log_error(message=frappe.get_traceback(), title="Temporary Worker HR notify failed"[:140])


def _hr_recipients() -> list:
    """Enabled users holding HR Manager (fallback: System Manager)."""
    from frappe.utils.user import get_users_with_role

    for role in ("HR Manager", "System Manager"):
        users = get_users_with_role(role)
        if users:
            return users
    return []
