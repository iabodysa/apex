# Copyright (c) 2026, AFMCO and contributors
# -*- coding: utf-8 -*-
# [#j03s5a]

from frappe.model.document import Document


class Site(Document):
    def onload(self):
        # [#qf3k0t]
        from frappe.contacts.address_and_contact import load_address_and_contact

        load_address_and_contact(self)
