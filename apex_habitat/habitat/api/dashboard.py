import frappe

@frappe.whitelist()
def get_compliance_percent():
    # Number of Completed vs Total Active Scheduled Task Instances.
    # Gate on read access to the underlying DocType so this metric cannot be
    # harvested by a user who could not otherwise see Scheduled Task Instances.
    frappe.has_permission("Scheduled Task Instance", "read", throw=True)
    total = frappe.db.count("Scheduled Task Instance", {"status": ["not in", ["Cancelled"]]})
    if not total:
        return 100.0
    completed = frappe.db.count("Scheduled Task Instance", {"status": "Completed"})
    return round((completed / total) * 100, 2)
