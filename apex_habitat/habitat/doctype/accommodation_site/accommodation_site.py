# -*- coding: utf-8 -*-
# [#m4uz3c]

from frappe.model.document import Document


class AccommodationSite(Document):
    def onload(self):
        # [#d2spls]
        # [#h4hqjz]
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)
