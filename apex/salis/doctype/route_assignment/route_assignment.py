# Copyright (c) 2026, afmcoltd
"""Route Assignment controller.

Links a Work Shift to a dispatch context.  Fetch chains populate shift details
automatically when a Work Shift is selected:

    work_shift  →  shift_name        (fetch_from: work_shift.shift_name)
    work_shift  →  shift_start_time  (fetch_from: work_shift.start_time)
    work_shift  →  shift_end_time    (fetch_from: work_shift.end_time)
    work_shift  →  project           (fetch_from: work_shift.project)

All fetched fields carry fetch_if_empty=1 so they can be overridden per
assignment if the operational context requires it.  Downstream DocTypes
(Dispatch Trip, Trip Start Log) pull shift identity from here via their own
fetch chains.
"""

from __future__ import annotations

from frappe.model.document import Document


class RouteAssignment(Document):
    pass
