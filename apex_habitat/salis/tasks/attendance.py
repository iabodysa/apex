# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe

from apex_habitat.salis.tasks.common import (
    BATCH_SIZE,
    _raise_alert,
)


def missing_attendance_watch() -> None:
    """Flag active drivers with no Driver Attendance recorded today.

    For each Salis Driver ``{status: Active}`` checks for a submitted Driver
    Attendance for today. If none exists, raises an Info "Supervisor Delay"
    alert (the Operations Alert DocType has no dedicated "Attendance Gap"
    option, so the nearest existing option is reused).
    """
    from frappe.utils import today

    today_str = today()
    logger = frappe.logger()

    # [#hww2kb]
    try:
        rows = frappe.db.sql(
            """
            SELECT driver
            FROM `tabDriver Attendance`
            WHERE docstatus = 1
              AND attendance_date = %(today)s
              AND driver IS NOT NULL
            GROUP BY driver
            """,
            {"today": today_str},
            as_dict=True,
        )
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
            try:
                if d.name in drivers_with_attendance:
                    continue
                # [#bces73]
                who = d.name
                msg = (f"missing_attendance_watch: no attendance recorded today for "
                       f"active driver {who}.")
                logger.warning(msg)
                _raise_alert("Supervisor Delay", "Info", msg,
                             "Salis Driver", d.name, driver=d.name)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Missing attendance watch failed for {d.name}"[:140],
                )

        start += BATCH_SIZE
