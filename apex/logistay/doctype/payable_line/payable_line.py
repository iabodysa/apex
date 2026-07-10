# Copyright (c) 2026, AFMCO and contributors
"""Payable Line controller — worker-side reconciliation output, GROSS (P-190).

Emitted by a Reconciliation Run and consumed by payroll (P-192). Machine-written
GROSS (pre-deduction); deductions are raised separately as Deduction Candidates
and never netted here. Carries the ``rec_day_rate_basis_applied`` snapshot the
run's BASIS-CONSISTENT guard compares against the paired Billable Line. Thin
controller; the run owns the cross-line guards.
"""

from __future__ import annotations

from frappe.model.document import Document


class PayableLine(Document):
    pass
