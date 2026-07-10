# Copyright (c) 2026, AFMCO and contributors
"""Rate Card Component Row - child of Rate Card.

One priced component line. The day-rate basis (C3) is per line, not one global
divisor. The money value is withheld from the committed structure and seeded
out-of-repo. The controller is intentionally thin; parent validation lives on
the Rate Card.
"""

from __future__ import annotations

from frappe.model.document import Document


class RateCardComponentRow(Document):
    pass
