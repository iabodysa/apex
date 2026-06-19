import frappe
from frappe.utils import flt

@frappe.whitelist()
def get_compliance_percent():
    # [#qh57p2]
    frappe.has_permission("Scheduled Task Instance", "read", throw=True)
    total = frappe.db.count("Scheduled Task Instance", {"status": ["not in", ["Cancelled"]]})
    if not total:
        return 100.0
    completed = frappe.db.count("Scheduled Task Instance", {"status": "Completed"})
    return round((completed / total) * 100, 2)


@frappe.whitelist()
def get_custody_value_in_employee_hands():
    """Value-at-risk: SAR currently held in employee custody. [T-277]

    Sums signed (qty * unit_cost_sar) over non-cancelled Custody Article rows of
    the Accommodation Stock Ledger where an employee is set — issue rows add,
    return rows reverse, so the net is exactly what workers still hold. One bounded
    grouped query; Custom Number Card return contract (scalar)."""
    frappe.has_permission("Accommodation Stock Ledger", "read", throw=True)
    total = frappe.db.sql(
        """
        SELECT COALESCE(SUM(qty * COALESCE(unit_cost_sar, 0)), 0)
        FROM `tabAccommodation Stock Ledger`
        WHERE is_cancelled = 0
          AND item_type = 'Custody Article'
          AND employee IS NOT NULL AND employee != ''
        """
    )
    return flt(total[0][0]) if total else 0.0
