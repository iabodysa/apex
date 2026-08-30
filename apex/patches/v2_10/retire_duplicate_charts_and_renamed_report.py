# Copyright (c) 2026, afmcoltd
import frappe

RETIRED_RECORDS = [
    ("Dashboard Chart", "Topups by Status"),
    ("Dashboard Chart", "Available Capacity Trend"),
    ("Dashboard Chart", "Findings by Severity"),
    ("Report", "Accommodation Ledger Summary"),
]


def execute():
    for doctype, name in RETIRED_RECORDS:
        frappe.delete_doc(doctype, name, ignore_missing=True, force=True)
