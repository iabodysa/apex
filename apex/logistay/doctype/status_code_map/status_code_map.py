# Copyright (c) 2026, AFMCO and contributors
"""Status Code Map controller - the canonical attendance vocabulary.

Maps free per-format source tokens onto the one canonical Timesheet Daily Status
enum. The controller guards only for duplicate tokens within one map; the lookup
+ override logic lives in ``logistay.ingestion_engine``.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class StatusCodeMap(Document):
    def validate(self) -> None:
        self._validate_unique_tokens()

    def _validate_unique_tokens(self) -> None:
        seen = set()
        for row in self.ts_token_rows or []:
            token = (row.source_token or "").strip().lower()
            if not token:
                continue
            if token in seen:
                frappe.throw(_("Source token {0} is mapped more than once.").format(row.source_token))
            seen.add(token)
