# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns = [
        {
                "label": frappe._("Building"),
                "fieldname": "building",
                "fieldtype": "Link",
                "options": "Accommodation Building",
                "width": 120
        },
        {
                "label": frappe._("Room"),
                "fieldname": "room",
                "fieldtype": "Link",
                "options": "Accommodation Room",
                "width": 100
        },
        {
                "label": frappe._("Bed"),
                "fieldname": "bed",
                "fieldtype": "Link",
                "options": "Accommodation Bed",
                "width": 100
        },
        {
                "label": frappe._("Occupant"),
                "fieldname": "employee",
                "fieldtype": "Link",
                "options": "Employee",
                "width": 150
        },
        {
                "label": frappe._("Check-in Date"),
                "fieldname": "check_in_date",
                "fieldtype": "Date",
                "width": 100
        },
        {
                "label": frappe._("Status"),
                "fieldname": "status",
                "fieldtype": "Select",
                "width": 100
        }
]
    data = []
    return columns, data
