# Copyright (c) 2026, AFMCO and contributors
import frappe

RETIRED_WORKSPACES = (
    "Backend Engines", "Compliance and Rentals", "Masar", "Operations",
    "Housing", "Safety", "Custody", "Costs and Leasing",
)

RETIRED_ONBOARDINGS = (
    "Accommodation Go-Live", "Safety Readiness", "Maintenance Daily Flow",
    "Custody Go-Live", "Masar Go-Live", "Salis Fuel Setup",
    "Compliance and Rentals Go-Live",
)


def execute():
    """Remove the workspaces and onboardings whose content moved elsewhere.

    A standard record that leaves the app is not removed by migrate — it stays behind and keeps
    rendering, because sync only imports what it finds on disk. A stale workspace shows an empty
    page in the sidebar; a stale onboarding offers a checklist for a page that is gone.
    """
    for name in RETIRED_WORKSPACES:
        if frappe.db.exists("Workspace", name):
            frappe.delete_doc(
                "Workspace", name, force=True,
                ignore_permissions=True,  # audit-ok: removes this app's own shipped record
            )

    for name in RETIRED_ONBOARDINGS:
        if frappe.db.exists("Module Onboarding", name):
            frappe.delete_doc(
                "Module Onboarding", name, force=True,
                ignore_permissions=True,  # audit-ok: removes this app's own shipped record
            )
