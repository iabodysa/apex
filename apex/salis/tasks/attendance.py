# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import today

from apex.salis.tasks.common import (
    BATCH_SIZE,
    _queue_document,
)

_ROW_SAVEPOINT = "salis_attendance_row"


def missing_attendance_watch() -> None:
    today_str = today()
    logger = frappe.logger()

    try:
        DA = frappe.qb.DocType("Driver Attendance")
        rows = (
            frappe.qb.from_(DA)
            .select(DA.driver)
            .where(DA.docstatus == 1)
            .where(DA.attendance_date == today_str)
            .where(DA.driver.isnotnull())
            .groupby(DA.driver)
        ).run(as_dict=True)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Missing attendance watch: attendance aggregate failed"[:140],
        )
        return
    drivers_with_attendance = {r["driver"] for r in rows}

    start = 0
    while True:
        drivers = frappe.get_all(
            "Salis Driver",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not drivers:
            break

        for d in drivers:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                if d.name in drivers_with_attendance:
                    continue
                who = d.name
                msg = (f"missing_attendance_watch: no attendance recorded today for "
                       f"active driver {who}.")
                logger.warning(msg)
                _queue_document("Salis Driver", d.name, "Info", msg)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Missing attendance watch failed for {d.name}"[:140],
                )

        start += BATCH_SIZE
