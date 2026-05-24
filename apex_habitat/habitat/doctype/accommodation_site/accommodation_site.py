# -*- coding: utf-8 -*-
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AccommodationSite(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        city: DF.Link | None
        district: DF.Data | None
        notes: DF.SmallText | None
        site_name: DF.Data
        status: DF.Literal["Active", "Inactive"]
    # end: auto-generated types
    pass


def before_save(doc, method=None):
    # Validate document properties
    if doc.doctype != "Accommodation Site":
        frappe.throw("DocType mismatch")
