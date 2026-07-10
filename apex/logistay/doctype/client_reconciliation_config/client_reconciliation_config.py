# Copyright (c) 2026, AFMCO and contributors
"""Client Reconciliation Config controller — per-client reconciliation inputs (P-190).

Holds the handoff SLA (D7) and the per-worker-feed flag (A2/C4 FED-PRECONDITION)
read by the reconciliation engine. The SLA number is seeded out-of-repo; only a
structural non-negative guard lives here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ClientReconciliationConfig(Document):
    def validate(self) -> None:
        if self.handoff_sla_days is not None and self.handoff_sla_days < 0:
            frappe.throw(_("Handoff SLA Days cannot be negative."))
