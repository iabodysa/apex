# Copyright (c) 2026, AFMCO and contributors
"""Rate Card Penalty Row - child of Rate Card.

Threshold + rule are committed structure; the amount / rate is withheld and
seeded out-of-repo, and the rule stays gated until the amount is set. Thin
controller; the reconciliation engine reads these parameters.
"""

from __future__ import annotations

from frappe.model.document import Document


class RateCardPenaltyRow(Document):
    pass
