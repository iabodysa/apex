# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.model.document import Document


class CustodyIssueItem(Document):
    def before_save(self):
        if not self.doctype:
            return
