# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class MaintenanceProcurementItem(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Maintenance Procurement Item":
            frappe.throw("DocType mismatch")
