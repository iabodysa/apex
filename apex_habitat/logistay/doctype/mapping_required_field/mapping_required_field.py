# Copyright (c) 2026, AFMCO and contributors
"""Mapping Required Field — child row of Mapping Profile.

One row per canonical field the profile requires, with its enforcement level:
GATE blocks the intake (an exception is logged), WARN logs and continues.
The controller is intentionally thin; enforcement lives in the ingestion
engine (E-INGEST).
"""

from __future__ import annotations

from frappe.model.document import Document


class MappingRequiredField(Document):
    pass
