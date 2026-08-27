# Copyright (c) 2026, afmcoltd

import frappe
from frappe.utils import add_days, get_datetime, getdate


def execute():
    if not frappe.db.table_exists("Driver Attendance"):
        return

    rows = frappe.db.sql(
        """
        select name, attendance_date, check_in, check_out
        from `tabDriver Attendance`
        where attendance_date is not null
          and (check_in is not null or check_out is not null)
        """,
        as_dict=True,
    )
    for row in rows:
        day = getdate(row.attendance_date)
        check_in = _moved_to(day, row.check_in)
        check_out = _moved_to(day, row.check_out)
        if check_in and check_out and check_out < check_in:
            check_out = _moved_to(add_days(day, 1), row.check_out)
        if check_in == row.check_in and check_out == row.check_out:
            continue
        frappe.db.set_value(
            "Driver Attendance",
            row.name,
            {"check_in": check_in, "check_out": check_out},
            update_modified=False,
        )


def _moved_to(day, stamp):
    if not stamp:
        return None
    day = getdate(day)
    return get_datetime(stamp).replace(year=day.year, month=day.month, day=day.day)
