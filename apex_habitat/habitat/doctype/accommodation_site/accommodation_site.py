# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AccommodationSite(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    if doc.doctype != "Accommodation Site":
        frappe.throw("DocType mismatch")
