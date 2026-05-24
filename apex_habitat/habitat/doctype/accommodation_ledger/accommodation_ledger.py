"""Accommodation Ledger controller.

Hidden, machine-written cost allocation ledger. No DocPerm grants write/create
to any human role; rows are inserted by scheduled jobs and hooks using
ignore_permissions. When GL posting is disabled in Habitat Settings, rows are
operational memos with no GL postings.
"""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationLedger(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return
