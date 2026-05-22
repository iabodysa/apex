# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": frappe._("Posting Date"),
                "fieldname": "posting_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": frappe._("Employee"),
                "fieldname": "employee",
                "fieldtype": "Link",
                "options": "Employee",
                "width": 150
        },
        {
                "label": frappe._("Building"),
                "fieldname": "building",
                "fieldtype": "Link",
                "options": "Accommodation Building",
                "width": 120
        },
        {
                "label": frappe._("Amount (SAR)"),
                "fieldname": "amount",
                "fieldtype": "Currency",
                "width": 100
        },
        {
                "label": frappe._("Ledger Type"),
                "fieldname": "ledger_type",
                "fieldtype": "Select",
                "width": 100
        }
]
    data = []
    return columns, data
