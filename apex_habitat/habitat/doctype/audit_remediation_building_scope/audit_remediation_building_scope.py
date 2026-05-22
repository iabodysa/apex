# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AuditRemediationBuildingScope(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Audit Remediation Building Scope":
            frappe.throw("DocType mismatch")
