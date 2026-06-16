# -*- coding: utf-8 -*-
# [#m4uz3c]

import frappe
from frappe.model.document import Document

class SubcontractorBuildingCoverage(Document):
    def before_save(self):
        # [#2qfbj3]
        if self.doctype != "Subcontractor Building Coverage":
            frappe.throw("DocType mismatch")
