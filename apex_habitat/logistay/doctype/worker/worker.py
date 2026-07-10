# Copyright (c) 2026, AFMCO and contributors
"""Worker controller.

Canonical workforce identity for the Logistay timesheet flow. A Worker is the
single party that attendance (Timesheet Line) and billing (Timesheet Ledger)
point at, independent of whether the person is a Temporary Worker, a Freelancer,
or a permanent Employee. The ``source_*`` / ``linked_employee`` links record
where the identity originated so the flow never has to branch on employment form.

Deliberately minimal: identity is a pure master with no lifecycle invariant of
its own, so no controller logic lives here yet. Reconciliation to the source
records (dedupe by Iqama, status roll-up) is a later, data-gated batch.
"""

from __future__ import annotations

from frappe.model.document import Document


class Worker(Document):
    pass
