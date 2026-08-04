# Copyright (c) 2026, AFMCO and contributors
# -*- coding: utf-8 -*-

from frappe.model.document import Document


class Site(Document):
    def onload(self):
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)
