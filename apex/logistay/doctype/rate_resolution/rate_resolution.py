# Copyright (c) 2026, AFMCO and contributors
"""Rate Resolution controller - append-only pricing log.

Reproducibility record: which Rate Card version priced one timesheet line and
the day rate + basis applied. It is immutable - once written it may not be
edited or deleted; a correction is a NEW resolution. The basis snapshot
(``rc_day_rate_basis_applied``) feeds the reconciliation engine's
basis-consistent guard.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class RateResolution(Document):
    def validate(self) -> None:
        if not self.is_new():
            frappe.throw(
                _("Rate Resolution is an append-only log and cannot be edited. "
                  "Record a new resolution instead.")
            )

    def on_trash(self) -> None:
        frappe.throw(_("Rate Resolution is an append-only log and cannot be deleted."))
