"""Apex Settings controller.

App-wide configuration shared by every Apex module (Habitat and Salis). Holds
settings that are not scoped to a single domain, such as the finance integration
defaults (``default_payment_method``, ``enable_gl_posting``) that govern how the
app generates payment documents and whether it posts to the General Ledger.
"""

from __future__ import annotations

from frappe.model.document import Document


class ApexSettings(Document):
    pass
