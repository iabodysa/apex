# Copyright (c) 2026, afmcoltd

from frappe.contacts.address_and_contact import load_address_and_contact
from frappe.model.document import Document

class Site(Document):
    def onload(self):
        load_address_and_contact(self)
