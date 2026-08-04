# Copyright (c) 2026, AFMCO and contributors
import frappe


def execute():
    """Remove the report whose rows the SIM Card list view now shows on its own.

    A standard record that leaves the app is not removed by migrate — sync only imports what it
    finds on disk — so the report keeps appearing in the report list on every site installed
    before this release, running code the app no longer ships.
    """
    if frappe.db.exists("Report", "Current SIM Custody"):
        frappe.delete_doc(
            "Report", "Current SIM Custody", force=True,
            ignore_permissions=True,  # audit-ok: removes this app's own shipped record
        )
