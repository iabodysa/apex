from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class AccommodationQRLocation(Document):
    def before_save(self):
        if not self.location_token:
            self.location_token = frappe.generate_hash(length=10)

        self.public_url = get_url(f"/qr-request?token={self.location_token}")
