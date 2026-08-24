# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today

from apex.salis.tasks.common import (
    BATCH_SIZE,
    _notify_fleet_role,
)

_ROW_SAVEPOINT = "salis_fuel_row"

def unreverted_topup_watch() -> None:
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
                    doc.save()
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
