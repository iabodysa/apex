# Copyright (c) 2026, afmcoltd

import frappe


def execute():
    """Fill party_type/party on existing Accommodation Stock Ledger rows.

    The holder column moved from employee to party_type/party so a Temporary Worker can
    hold stock. Balances read the new column, so every historical custody row has to
    carry it or it would read as unassigned store stock from the moment the field lands.
    """
    if not frappe.db.has_column("Accommodation Stock Ledger", "party"):
        return
    frappe.db.sql(
        """
        UPDATE `tabAccommodation Stock Ledger`
        SET party_type = 'Employee', party = employee
        WHERE ifnull(employee, '') != '' AND ifnull(party, '') = ''
        """
    )
