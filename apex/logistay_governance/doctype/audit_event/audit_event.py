# Copyright (c) 2026, AFMCO and contributors
"""Audit Event controller.

The immutable, append-only cross-entity governance log. Once written a row can
never be edited or deleted; a correction is a NEW compensating event. Immutability
is defended two ways: the DocPerm rows grant no ``write``/``delete`` to any role,
and the controller hard-blocks any update or trash even for an ``ignore_permissions``
caller. Rows are inserted only by the shared ``write_audit`` service.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AuditEvent(Document):
    def validate(self) -> None:
        # validate() fires on both insert and update; an update means someone is
        # mutating a written event -> refuse. is_new() is True only pre-insert.
        if not self.is_new():
            frappe.throw(
                _("Audit Event is append-only; record a new compensating event instead of editing.")
            )
        if not self.gov_at:
            self.gov_at = now_datetime()

    def on_trash(self) -> None:
        frappe.throw(_("Audit Event is immutable and cannot be deleted."))
