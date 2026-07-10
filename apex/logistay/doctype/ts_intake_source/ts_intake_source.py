# Copyright (c) 2026, AFMCO and contributors
"""TS Intake Source controller - one raw upload / source batch for ingestion.

The operator files a client/supervisor artifact plus its extracted JSON payload.
The controller only sanity-checks the payload is parseable JSON; the parse +
merge + gap-check pipeline lives in ``logistay.ingestion_engine``.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document


class TSIntakeSource(Document):
    def validate(self) -> None:
        self._validate_payload_json()

    def _validate_payload_json(self) -> None:
        raw = (self.ts_payload or "").strip()
        if not raw:
            return
        try:
            json.loads(raw)
        except (ValueError, TypeError):
            frappe.throw(_("Payload must be valid JSON."))
