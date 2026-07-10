# Copyright (c) 2026, AFMCO and contributors
"""Billable Line controller — client-side reconciliation output (P-190).

Emitted by a Reconciliation Run and consumed by the invoice generator (P-191).
Machine-written: amounts are computed by the reconciliation function, never
hand-keyed. Carries the ``rec_day_rate_basis_applied`` snapshot the run's
BASIS-CONSISTENT guard compares against the paired Payable Line. Thin
controller; the run owns the cross-line guards.
"""

from __future__ import annotations

from frappe.model.document import Document


class BillableLine(Document):
    pass
