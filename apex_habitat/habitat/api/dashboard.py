import frappe

@frappe.whitelist()
def get_compliance_percent():
    # [#qh57p2]
    frappe.has_permission("Scheduled Task Instance", "read", throw=True)
    total = frappe.db.count("Scheduled Task Instance", {"status": ["not in", ["Cancelled"]]})
    if not total:
        return 100.0
    completed = frappe.db.count("Scheduled Task Instance", {"status": "Completed"})
    return round((completed / total) * 100, 2)
