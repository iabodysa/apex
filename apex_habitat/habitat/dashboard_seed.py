"""Seed the native Habitat Dashboard (Beds by Status chart) as a data record.

Frappe does not reliably auto-sync a standalone is_standard Dashboard fixture on
migrate, so we create it idempotently here (mirrors the notification/kanban seeds).
Linked from the Habitat workspace via a Dashboard workspace link.
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
