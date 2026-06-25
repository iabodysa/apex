import frappe
from frappe.utils import flt, today

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
def get_buildings_over_threshold(filters=None):
    """Count buildings whose occupancy exceeds their OWN over-capacity threshold.

    Row-relative (each building's occupancy_percent vs its own
    over_capacity_threshold_percent) — a static Document Type filter cannot
    compare two fields, so this is a Custom Number Card. An unset/zero threshold
    falls back to the field default (120) rather than counting as a 0% threshold.
    """
    frappe.has_permission("Accommodation Building", "read", throw=True)
    row = frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabAccommodation Building`
        WHERE occupancy_percent > COALESCE(NULLIF(over_capacity_threshold_percent, 0), 120)
        """
    )
    return int(row[0][0]) if row else 0


@frappe.whitelist()
def get_arrivals_today():
    """Count workers housed today: submitted Accommodation Assignments whose
    check_in_date is today. Custom (not a Document Type filter) so the date is
    resolved server-side on each render rather than frozen into a saved filter.
    Scalar Custom Number Card return contract."""
    frappe.has_permission("Accommodation Assignment", "read", throw=True)
    return frappe.db.count(
        "Accommodation Assignment",
        {"check_in_date": today(), "docstatus": 1},
    )


@frappe.whitelist()
def get_pending_on_manifest():
    """Workers still unhoused against arrival manifests due on/before today.

    Mirrors ArrivalBatch.pending_arrival_count (expected_count minus those
    actually housed in the building on the expected date), summed across all
    Arrival Batches whose expected_date has arrived. One bounded grouped query
    instead of loading each batch; negatives (over-arrival) clamp to 0 so they
    never offset another batch's shortfall. Scalar return contract."""
    frappe.has_permission("Arrival Batch", "read", throw=True)
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(GREATEST(b.expected_count - COALESCE(h.housed, 0), 0)), 0)
        FROM `tabArrival Batch` b
        LEFT JOIN (
            SELECT building, check_in_date, COUNT(*) AS housed
            FROM `tabAccommodation Assignment`
            WHERE docstatus = 1
            GROUP BY building, check_in_date
        ) h ON h.building = b.building AND h.check_in_date = b.expected_date
        WHERE b.expected_date <= %(today)s
        """,
        {"today": today()},
    )
    return int(row[0][0]) if row else 0


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
