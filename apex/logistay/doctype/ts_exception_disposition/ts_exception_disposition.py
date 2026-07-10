# Copyright (c) 2026, AFMCO and contributors
"""TS Exception Disposition controller - dispose an exception group.

Companion record for the immutable Timesheet Exception Log: one disposition
covers every log row sharing the same (type, entity, period, field) group. The
controller derives the stable group key, enforces a reason on a waiver, stamps
who/when, and snapshots how many log rows the group covered.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from apex.logistay.api.exception_workbench import (
    EXCEPTION_LOG_DOCTYPE,
    exception_group_key,
)


class TSExceptionDisposition(Document):
    def validate(self) -> None:
        self.group_key = exception_group_key(
            self.exception_type, self.entity, self.period_month, self.field_ref
        )
        if self.disposition == "Waived" and not (self.reason or "").strip():
            frappe.throw(_("A reason is required to waive an exception."))
        if not self.disposed_by:
            self.disposed_by = frappe.session.user
        if not self.disposed_at:
            self.disposed_at = now_datetime()
        self.matched_count = frappe.db.count(
            EXCEPTION_LOG_DOCTYPE, self._group_filters()
        )

    def _group_filters(self) -> dict:
        filters = {"exception_type": self.exception_type, "entity": self.entity}
        # [#oha5ax]
        filters["period_month"] = self.period_month or ["in", [None, ""]]
        filters["field_ref"] = self.field_ref or ["in", [None, ""]]
        return filters
