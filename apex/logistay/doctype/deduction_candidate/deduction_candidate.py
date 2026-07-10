# Copyright (c) 2026, AFMCO and contributors
"""Deduction Candidate controller — the performance-to-money link (P-190).

Emitted by a Reconciliation Run as a CANDIDATE only. It is never finalized
here: the amount is gated on the owner-confirmed penalty thresholds and the
worker consent gate lives in payroll (P-192). rec_requires_consent defaults to
1 so nothing is deducted without a verified consent downstream. Thin
controller; finalization is out of scope for the reconciliation side.
"""

from __future__ import annotations

from frappe.model.document import Document


class DeductionCandidate(Document):
    pass
