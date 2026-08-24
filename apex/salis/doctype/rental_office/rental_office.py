# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document


class RentalOffice(Document):
    def validate(self):
        if self.office_name:
            self.office_name = self.office_name.strip()
