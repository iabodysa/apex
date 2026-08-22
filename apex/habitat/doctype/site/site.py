# Copyright (c) 2026, afmcoltd

from frappe.model.document import Document

class Site(Document):
    def onload(self):
        """Loads the site's linked addresses and contacts into the document on open."""
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)
