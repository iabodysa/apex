# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class CleaningLogRoomDetail(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Cleaning Log Room Detail":
            frappe.throw("DocType mismatch")
