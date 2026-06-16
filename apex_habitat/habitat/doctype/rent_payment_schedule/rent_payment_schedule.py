# -*- coding: utf-8 -*-
# [#m4uz3c]

import frappe
from frappe.model.document import Document

class RentPaymentSchedule(Document):
    def before_save(self):
        # [#2qfbj3]
        if self.doctype != "Rent Payment Schedule":
            frappe.throw("DocType mismatch")
