# Copyright (c) 2026, afmcoltd
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
    "Current SIM Custody",
]


def execute():
    """Deletes the Auto Email Reports, Report records, and onboarding step for the retired reports."""
    for aer in frappe.get_all(
        "Auto Email Report", filters={"report": ["in", RETIRED_REPORTS]}, pluck="name"
    ):
        frappe.delete_doc("Auto Email Report", aer, ignore_missing=True, force=True)
    for name in RETIRED_REPORTS:
        frappe.delete_doc("Report", name, ignore_missing=True, force=True)
    frappe.delete_doc(
        "Onboarding Step", "Review the Active Resident Register", ignore_missing=True, force=True
    )
