# Copyright (c) 2026, afmcoltd
import frappe

RETIRED_RECORDS = [
    ("Number Card", "Open Theft Reports"),
    ("Dashboard Chart", "Operating Days Trend"),
]


def execute():
    for doctype, name in RETIRED_RECORDS:
        frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
