# Copyright (c) 2026, AFMCO and contributors
"""Rate Card Enabled Component - multiselect child of Rate Card.

One row per enabled billing component, pointing at a Rate Card Component Type.
Thin controller.
"""

from __future__ import annotations

from frappe.model.document import Document


class RateCardEnabledComponent(Document):
    pass
