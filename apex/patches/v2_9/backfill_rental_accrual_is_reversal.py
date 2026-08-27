# Copyright (c) 2026, afmcoltd

import frappe

from apex.salis.doctype.rental_accrual_ledger.rental_accrual_ledger import on_doctype_update


def execute():
    if "is_reversal" not in frappe.db.get_table_columns("Rental Accrual Ledger"):
        return
    frappe.db.sql(
        """
        UPDATE `tabRental Accrual Ledger`
        SET is_reversal = 1
        WHERE reversal_of IS NOT NULL AND reversal_of != '' AND is_reversal = 0
        """
    )
    on_doctype_update()
