# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class QRLocation(Document):
    pass


def before_save(doc, method=None):
    if not doc.location_token:
        doc.location_token = frappe.generate_hash(length=10)

    doc.public_url = get_url(f"/qr-request?token={doc.location_token}")
