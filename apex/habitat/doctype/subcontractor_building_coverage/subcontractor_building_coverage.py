# Copyright (c) 2026, afmcoltd
# -*- coding: utf-8 -*-

import frappe
from frappe.model.document import Document

class SubcontractorBuildingCoverage(Document):
    def before_save(self):
        """Blocks saving when the loaded document's doctype is not Subcontractor Building Coverage."""
        if self.doctype != "Subcontractor Building Coverage":
            frappe.throw("DocType mismatch")
