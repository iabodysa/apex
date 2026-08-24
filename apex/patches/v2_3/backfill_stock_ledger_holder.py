# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    if not frappe.db.has_column("Accommodation Stock Ledger", "party"):
        return
    frappe.db.sql(
        """
        UPDATE `tabAccommodation Stock Ledger`
        SET party_type = 'Employee', party = employee
        WHERE ifnull(employee, '') != '' AND ifnull(party, '') = ''
        """
    )
