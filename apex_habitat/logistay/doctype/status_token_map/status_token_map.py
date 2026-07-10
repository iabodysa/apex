# Copyright (c) 2026, AFMCO and contributors
"""Status Token Map - one source-token to canonical-status mapping row.

Child of Status Code Map; has no independent lifecycle.
"""

from __future__ import annotations

from frappe.model.document import Document


class StatusTokenMap(Document):
    pass
