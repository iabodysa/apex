# Copyright (c) 2026, AFMCO and contributors
"""Work Shift controller.

Master record for a named operational shift within a project.
Each shift defines a daily start/end time window and the weekdays on which it
applies.  It is the source-of-truth for the fetch chain:

    Work Shift  →  Route Assignment  →  Dispatch Trip  →  Trip Start Log

The controller is intentionally thin: it enforces only the time-ordering
invariant (end_time must be after start_time for same-day shifts) and delegates
all workflow behaviour to native Frappe fetch_from declarations on the linking
DocTypes.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class WorkShift(Document):
    def validate(self):
        self._validate_shift_times()

    def _validate_shift_times(self):
        """End Time must be after Start Time (same-day shifts only).

        Cross-midnight shifts (end < start) are legitimate in some operations
        contexts, but this app currently assumes same-day windows.  The guard
        can be relaxed by removing this method when cross-midnight support is
        needed.
        """
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            frappe.throw(
                _("End Time must be later than Start Time for shift {0}.").format(
                    self.shift_name or self.name
                )
            )
