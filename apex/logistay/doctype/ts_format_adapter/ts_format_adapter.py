# Copyright (c) 2026, AFMCO and contributors
"""TS Format Adapter controller - the parser registry.

One row per parser kind a Mapping Profile can bind to. A pure config master; the
parser selection logic lives in ``logistay.ingestion_engine``.
"""

from __future__ import annotations

from frappe.model.document import Document


class TSFormatAdapter(Document):
    pass
