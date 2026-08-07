# Copyright (c) 2026, AFMCO and contributors
import frappe

RETIRED_REPORTS = [
    "Open Maintenance Requests",
    "Custody Outstanding by Worker",
    "Safety Task Execution Log",
    "Movement Cost Recovery Register",
    "Active Resident Register",
    "Custody Damage Register",
    "SIMs by Contract and Supplier",
    "Fleet Register",
    "Daily Cleaning Compliance",
    "Safety Task Compliance Summary",
    "Occupancy Trend",
    "Transport Fulfilment SLA",
    "Movement KPI Summary",
    "Fuel Consumption Summary",
]


def execute():
    for name in RETIRED_REPORTS:
        frappe.delete_doc("Auto Email Report", name, ignore_missing=True, force=True)
        frappe.delete_doc("Report", name, ignore_missing=True, force=True)
    frappe.delete_doc(
        "Onboarding Step", "Review the Active Resident Register", ignore_missing=True, force=True
    )
