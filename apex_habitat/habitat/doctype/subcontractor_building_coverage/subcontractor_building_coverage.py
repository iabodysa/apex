# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class SubcontractorBuildingCoverage(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Subcontractor Building Coverage":
            frappe.throw("DocType mismatch")
