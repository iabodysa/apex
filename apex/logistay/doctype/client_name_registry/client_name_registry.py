# Copyright (c) 2026, AFMCO and contributors
"""Client Name Registry controller - the naming-mismatch pre-issue gate master.

Thin: it only holds the exact legal name + VAT/CR a client's e-invoice must
carry (both WITHHELD, seeded out-of-repo). The match itself runs at Sales
Invoice ``before_submit`` in ``logistay.invoice_assembly.naming_matches``.
"""

from __future__ import annotations

from frappe.model.document import Document


class ClientNameRegistry(Document):
    pass
