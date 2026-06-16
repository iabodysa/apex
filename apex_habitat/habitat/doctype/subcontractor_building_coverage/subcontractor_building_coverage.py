# -*- coding: utf-8 -*-
# [#j03s5a]

import frappe
from frappe.model.document import Document

class SubcontractorBuildingCoverage(Document):
    def before_save(self):
        # [#tgyggb]
        if self.doctype != "Subcontractor Building Coverage":
            frappe.throw("DocType mismatch")
