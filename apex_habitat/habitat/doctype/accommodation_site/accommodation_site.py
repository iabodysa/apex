# -*- coding: utf-8 -*-
# For license information, please see license.txt

from frappe.model.document import Document


class AccommodationSite(Document):
    def onload(self):
        # Populate __onload.addr_list so the native Address widget (address_html)
        # renders the linked Address records and the "New Address" button.
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)
