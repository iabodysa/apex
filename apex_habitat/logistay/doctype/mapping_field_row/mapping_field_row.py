# Copyright (c) 2026, AFMCO and contributors
"""Mapping Field Row — child row of Mapping Profile.

One row per source column/token mapped to a canonical Timesheet Line field,
with an optional transform. The no-code half of ingestion: a new client
format is a new set of these rows, not a new parser. The controller is
intentionally thin; validation lives on the Mapping Profile parent.
"""

from __future__ import annotations

from frappe.model.document import Document


class MappingFieldRow(Document):
    pass
