"""Seed the native Habitat Dashboards as data records.

Frappe does not reliably auto-sync a standalone is_standard Dashboard fixture on
migrate, so we create them idempotently here.
"""

import frappe


def seed_habitat_dashboard():
    if frappe.db.exists("Dashboard", "Habitat Dashboard"):
        return
    if not frappe.db.exists("Dashboard Chart", "Beds by Status"):
        return
    doc = frappe.get_doc({
        "doctype": "Dashboard",
        "dashboard_name": "Habitat Dashboard",
        "module": "Habitat",
        "is_default": 0,
        "is_standard": 0,
        "charts": [{"chart": "Beds by Status", "width": "Half"}],
    })
    doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()


def seed_role_dashboards():
    dashboards = [
        {
            "name": "Accommodation Manager Dashboard",
            "cards": ["Total Occupancy Percent", "Available Beds", "Imminent Checkouts"],
            "charts": [{"chart": "Beds by Status", "width": "Half"}, {"chart": "Beds by Building", "width": "Half"}]
        },
        {
            "name": "Resident Supervisor Dashboard",
            "cards": ["Open Resident Requests", "Overdue Safety Tasks", "Custody Items Pending Return"],
            "charts": [
                {"chart": "Requests by Status", "width": "Half"},
                {"chart": "Requests by Priority", "width": "Half"},
                {"chart": "Work Orders by Status", "width": "Full"}
            ]
        },
        {
            "name": "Finance Manager Dashboard",
            "cards": ["Active Lease Contracts", "Pending Utility Bills"],
            "charts": [{"chart": "Monthly Cost Bleeding", "width": "Half"}, {"chart": "Leases by Status", "width": "Half"}]
        },
        {
            "name": "Internal Auditor Dashboard",
            "cards": ["Compliance Percent", "Expiring Licenses", "Idle Residents"],
            "charts": [{"chart": "Safety Inspections Over Time", "width": "Half"}, {"chart": "Findings by Severity", "width": "Half"}]
        }
    ]
    for d in dashboards:
        cards_list = [{"card": c} for c in d["cards"]]
        charts_list = d["charts"]
        
        if frappe.db.exists("Dashboard", d["name"]):
            doc = frappe.get_doc("Dashboard", d["name"])
            doc.cards = []
            doc.charts = []
            for c in cards_list:
                doc.append("cards", c)
            for ch in charts_list:
                doc.append("charts", ch)
            doc.save(ignore_permissions=True)  # audit-ok
        else:
            doc = frappe.get_doc({
                "doctype": "Dashboard",
                "dashboard_name": d["name"],
                "module": "Habitat",
                "is_default": 0,
                "is_standard": 0,
                "cards": cards_list,
                "charts": charts_list
            })
            doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
