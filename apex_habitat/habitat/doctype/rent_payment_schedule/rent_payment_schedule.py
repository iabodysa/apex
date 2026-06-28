# Copyright (c) 2026, AFMCO and contributors
# -*- coding: utf-8 -*-
# [#j03s5a]

import frappe
from frappe.model.document import Document

class RentPaymentSchedule(Document):
    def before_save(self):
        # [#tgyggb]
        if self.doctype != "Rent Payment Schedule":
            frappe.throw("DocType mismatch")
