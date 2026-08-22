# Copyright (c) 2026, afmcoltd
"""Scheduled tasks for the Salis fleet module (split by domain).

The save passes ``ignore_permissions`` because the scheduler runs with no session user and the
watch flags a top-up nobody reverted — the record it touches belongs to the operator who raised
the request, not to the job, so there is no owner this could run as instead.
"""

from __future__ import annotations

import frappe
from frappe import _

from apex.salis.tasks.common import (
    BATCH_SIZE,
    _notify_fleet_role,
)

_ROW_SAVEPOINT = "salis_fuel_row"

def unreverted_topup_watch() -> None:
    """Auto-revert temporary fuel top-ups that are past their revert-due date,
    then raise an alert for each.

    Reads Fuel Request ``{request_type: Top-up, is_temporary: 1, reverted: 0,
    status in [Approved, Done], revert_due_date: < today}``. For each overdue
    row it loads the document, sets ``reverted = 1`` and ``status = Reverted``,
    saves it (the change is captured natively by Version / track_changes), and
    NOTIFIES the Fleet Supervisors. Notify, not assign: the job has already fixed
    the condition it found, so this is a notice of an action taken — an assignment
    would be born settled and the next reconcile pass would close it unread.

    Each row is guarded in its own ``try/except`` (rollback + log) so one
    failure never aborts the batch. No ``commit()`` inside the loop — the
    scheduler commits the job transaction on success.
    """
    from frappe.utils import today

    today_str = today()
    logger = frappe.logger()

    cursor = ""
    while True:
        topups = frappe.get_all(
            "Fuel Request",
            filters={
                "request_type": "Top-up",
                "is_temporary": 1,
                "reverted": 0,
                "status": "Done",
                "revert_due_date": ["<", today_str],
                "name": [">", cursor],
            },
            fields=["name", "vehicle", "driver", "revert_due_date", "topup_litres"],
            order_by="name asc",
            limit_page_length=BATCH_SIZE,
        )
        if not topups:
            break

        for t in topups:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                doc = frappe.get_doc("Fuel Request", t.name)
                doc.reverted = 1
                doc.status = "Reverted"
                actor = frappe.session.user
                frappe.set_user("Administrator")
                try:
                    doc.save(ignore_permissions=True)
                finally:
                    frappe.set_user(actor)
                doc.add_comment(
                    "Info",
                    _("Auto-reverted: overdue temporary top-up (was due {0}).").format(
                        t.revert_due_date
                    ),
                )

                msg = (f"unreverted_topup_watch: temporary top-up {t.name} "
                       f"({t.topup_litres} L) was due to be reverted on "
                       f"{t.revert_due_date}; it has now been auto-reverted.")
                logger.warning(msg)
                _notify_fleet_role(
                    _("Overdue temporary top-up {0} was auto-reverted").format(t.name),
                    msg,
                    document_type="Fuel Request",
                    document_name=t.name,
                )
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Unreverted top-up watch failed for {t.name}"[:140],
                )

        cursor = topups[-1].name

    _flag_overdue_approved_topups(today_str, logger)

def _flag_overdue_approved_topups(today_str: str, logger) -> None:
    """Tell the fleet about overdue temporary top-ups still sitting at Approved.

    These cannot be auto-reverted: nothing was dispensed yet, and the workflow offers no
    Approved-to-Reverted transition. Someone has to Complete or Cancel them, so they are
    surfaced rather than left for a reader who would have to know to look.
    """
    stranded = frappe.get_all(
        "Fuel Request",
        filters={
            "request_type": "Top-up",
            "is_temporary": 1,
            "reverted": 0,
            "status": "Approved",
            "revert_due_date": ["<", today_str],
        },
        fields=["name", "revert_due_date", "topup_litres"],
        order_by="revert_due_date asc",
        limit_page_length=BATCH_SIZE,
    )
    for row in stranded:
        msg = (f"unreverted_topup_watch: temporary top-up {row.name} "
               f"({row.topup_litres} L) passed its revert date {row.revert_due_date} "
               f"while still Approved; it was never dispensed, so complete it or cancel it.")
        logger.warning(msg)
        _notify_fleet_role(
            _("Overdue temporary top-up {0} is still awaiting completion").format(row.name),
            msg,
            document_type="Fuel Request",
            document_name=row.name,
        )
