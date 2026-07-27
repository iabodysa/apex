# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.utils import flt, today
from frappe.query_builder.functions import Coalesce, Count
from pypika.functions import NullIf
from apex.habitat.permissions import _building_condition, report_building_scope

# [#eyjxdy]
@frappe.whitelist()
def get_compliance_percent(filters=None):
    # [#qh57p2]
    frappe.has_permission("Scheduled Task Instance", "read", throw=True)
    total = frappe.db.count("Scheduled Task Instance", {"status": ["not in", ["Cancelled"]]})
    if not total:
        return {"value": 100.0, "fieldtype": "Percent", "precision": 2}
    completed = frappe.db.count("Scheduled Task Instance", {"status": "Completed"})
    return {"value": round((completed / total) * 100, 2), "fieldtype": "Percent", "precision": 2}


@frappe.whitelist()
def get_buildings_over_threshold(filters=None):
    """Count buildings whose occupancy exceeds their OWN over-capacity threshold.

    Row-relative (each building's occupancy_percent vs its own
    over_capacity_threshold_percent) — a static Document Type filter cannot
    compare two fields, so this is a Custom Number Card. An unset/zero threshold
    falls back to the field default (120) rather than counting as a 0% threshold.

    Row scope is spliced explicitly: ``frappe.qb`` never consults
    ``permission_query_conditions``, so without this a building-scoped supervisor
    would be told how many buildings are over capacity ACROSS the whole estate.
    """
    frappe.has_permission("Building", "read", throw=True)
    # Here the estate axis is the Building's own name, not a `building` link.
    restrict, allowed = report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return {"value": 0, "fieldtype": "Int"}

    Building = frappe.qb.DocType("Building")
    # [#rccxmo]
    threshold = Coalesce(NullIf(Building.over_capacity_threshold_percent, 0), 120)
    query = (
        frappe.qb.from_(Building)
        .select(Count(Building.name))
        .where(Building.occupancy_percent > threshold)
    )
    if restrict:
        query = query.where(Building.name.isin(allowed))
    row = query.run()
    return {"value": int(row[0][0]) if row else 0, "fieldtype": "Int"}


@frappe.whitelist()
def get_arrivals_today(filters=None):
    """Count workers housed today: submitted Accommodation Assignments whose
    check_in_date is today. Custom (not a Document Type filter) so the date is
    resolved server-side on each render rather than frozen into a saved filter.

    Row scope is spliced explicitly: ``frappe.db.count`` builds its query through
    ``frappe.qb.get_query``, which never consults ``permission_query_conditions``,
    so the estate filter the Assignment LIST gets is absent here."""
    frappe.has_permission("Housing Assignment", "read", throw=True)
    restrict, allowed = report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return {"value": 0, "fieldtype": "Int"}

    filters = {"check_in_date": today(), "docstatus": 1}
    if restrict:
        filters["building"] = ["in", allowed]
    count = frappe.db.count("Housing Assignment", filters)
    return {"value": count, "fieldtype": "Int"}


@frappe.whitelist()
def get_pending_on_manifest(filters=None):
    """Workers still unhoused against arrival manifests due on/before today.

    Mirrors ArrivalBatch.pending_arrival_count (expected_count minus those
    actually housed in the building on the expected date), summed across all
    Arrival Batches whose expected_date has arrived. One bounded grouped query
    instead of loading each batch; negatives (over-arrival) clamp to 0 so they
    never offset another batch's shortfall.

    Row scope is spliced explicitly: raw SQL never consults
    ``permission_query_conditions``, so without the estate predicate a scoped
    supervisor would be shown the whole estate's manifest gap. Scoping the outer
    Arrival Batch is enough — the housed subquery only ever joins back on an
    in-scope building."""
    frappe.has_permission("Arrival Batch", "read", throw=True)
    restrict, allowed = report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return {"value": 0, "fieldtype": "Int"}

    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(GREATEST(b.expected_count - COALESCE(h.housed, 0), 0)), 0)
        FROM `tabArrival Batch` b
        LEFT JOIN (
            SELECT building, check_in_date, COUNT(*) AS housed
            FROM `tabHousing Assignment`
            WHERE docstatus = 1
            GROUP BY building, check_in_date
        ) h ON h.building = b.building AND h.check_in_date = b.expected_date
        WHERE b.expected_date <= %(today)s
          AND (%(unscoped)s = 1 OR b.building IN %(buildings)s)
        """,
        {
            "today": today(),
            "unscoped": 0 if restrict else 1,
            # Bound as a sequence so the query TEXT stays a literal (no
            # interpolation). The unscoped placeholder row exists only because
            # `IN ()` is a MariaDB syntax error; the flag above discards it.
            "buildings": tuple(allowed) if restrict else ("",),
        },
    )
    return {"value": int(row[0][0]) if row else 0, "fieldtype": "Int"}


@frappe.whitelist()
def get_custody_value_in_employee_hands(filters=None):
    """Value-at-risk: SAR currently held in employee custody. [T-277]

    Sums signed (qty * unit_cost) over non-cancelled Custody Article rows of
    the Accommodation Stock Ledger where an employee is set — issue rows add,
    return rows reverse, so the net is exactly what workers still hold. One bounded
    grouped query."""
    frappe.has_permission("Accommodation Stock Ledger", "read", throw=True)
    building_cond = _building_condition()
    extra = f"AND {building_cond}" if building_cond else ""
    total = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(signed_qty * COALESCE(unit_cost, 0)), 0)
        FROM `tabAccommodation Stock Ledger`
        WHERE is_cancelled = 0
          AND item_type = 'Custody Article'
          AND employee IS NOT NULL AND employee != ''
          {extra}
        """
    )
    return {"value": flt(total[0][0]) if total else 0.0, "fieldtype": "Currency", "options": "SAR"}


def get_top_custody_holders_by_value(limit: int = 10) -> list[dict]:
    """Top holders by outstanding custody value, same definition as the
    value-in-hands card and the Outstanding-by-Worker report — net signed
    (qty * unit_cost) over non-cancelled Custody Article rows with an employee
    set, grouped by employee. Holders whose net value is not positive are dropped.
    One bounded grouped query; returns ``[{employee, value}]`` value-desc."""
    building_cond = _building_condition()
    extra = f"AND {building_cond}" if building_cond else ""
    rows = frappe.db.sql(
        f"""
        SELECT employee, COALESCE(SUM(signed_qty * COALESCE(unit_cost, 0)), 0) AS value
        FROM `tabAccommodation Stock Ledger`
        WHERE is_cancelled = 0
          AND item_type = 'Custody Article'
          AND employee IS NOT NULL AND employee != ''
          {extra}
        GROUP BY employee
        HAVING value > 0
        ORDER BY value DESC
        LIMIT %(limit)s
        """,
        {"limit": int(limit)},
        as_dict=True,
    )
    return rows or []
