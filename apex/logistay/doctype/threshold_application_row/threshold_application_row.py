# Copyright (c) 2026, AFMCO and contributors
"""Threshold Application Row — child audit of which penalty rule fired (P-190).

One row per worker-threshold evaluated on a Reconciliation Run. rec_gated_open_item
marks an INFERRED (not owner-confirmed) rule; the run controller forces such a run
to PENDING-REVIEW and blocks POST. Thin child controller.
"""

from __future__ import annotations

from frappe.model.document import Document


class ThresholdApplicationRow(Document):
    pass
