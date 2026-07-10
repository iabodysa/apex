# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Daily Cleaning Compliance.

The compliance fact (rooms total / rooms cleaned / compliance %) is read from
the immutable Cleaning Compliance Ledger, NOT from the mutable Cleaning Log Room
Detail child rows. Each cleaned room posts one live ledger row on Cleaning Log
submit, and a cancel/amend posts a negating reversal (both rows flagged
is_cancelled), so a historical compliance figure does not change when the source
Cleaning Log is later edited or cancelled. Only live rows (is_cancelled=0) feed
the numerator/denominator.

The supervisory columns (cleaner type, approval, rating, missed/rework flags,
missed reason, scheduled task) are NOT posted facts — they are review state on
the parent Cleaning Log — so they are enriched best-effort from the live log.
They describe the log's current review status, while the compliance figure is the
stable posted fact this report exists to protect.
"""

import frappe
from frappe.utils import getdate, today, add_days

from apex_habitat.habitat import permissions

LEDGER_DOCTYPE = "Cleaning Compliance Ledger"


def execute(filters=None):
    filters = filters or {}

    date_from = getdate(filters.get("date_from") or add_days(today(), -7))
    date_to = getdate(filters.get("date_to") or today())

    columns = [
        {"label": frappe._("Log"), "fieldname": "name", "fieldtype": "Link", "options": "Cleaning Log", "width": 140},
        {"label": frappe._("Date"), "fieldname": "cleaning_date", "fieldtype": "Date", "width": 100},
        {"label": frappe._("Building"), "fieldname": "building", "fieldtype": "Link", "options": "Building", "width": 160},
        {"label": frappe._("Cleaner Type"), "fieldname": "cleaner_type", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Cleaner"), "fieldname": "cleaner", "fieldtype": "Data", "width": 140},
        {"label": frappe._("Rooms Total"), "fieldname": "rooms_total", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Rooms Cleaned"), "fieldname": "rooms_cleaned", "fieldtype": "Int", "width": 100},
        {"label": frappe._("Compliance %"), "fieldname": "compliance_pct", "fieldtype": "Float", "precision": 1, "width": 100},
        {"label": frappe._("Supervisor Approved"), "fieldname": "supervisor_approved", "fieldtype": "Check", "width": 130},
        {"label": frappe._("Rating"), "fieldname": "supervisor_rating", "fieldtype": "Data", "width": 90},
        {"label": frappe._("Missed"), "fieldname": "missed_cleaning", "fieldtype": "Check", "width": 70},
        {"label": frappe._("Rework Required"), "fieldname": "rework_required", "fieldtype": "Check", "width": 110},
        {"label": frappe._("Missed Reason"), "fieldname": "missed_reason", "fieldtype": "Data", "width": 180},
        {"label": frappe._("Scheduled Task"), "fieldname": "scheduled_task_instance", "fieldtype": "Link", "options": "Scheduled Task Instance", "width": 140},
    ]

    # The compliance fact comes from the immutable ledger: one live row per
    # cleaned room, posting_date == the source log's cleaning_date.
    ledger_filters = {
        "posting_date": ["between", [str(date_from), str(date_to)]],
        "is_cancelled": 0,
    }
    if filters.get("building"):
        ledger_filters["building"] = filters["building"]

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions — re-apply the caller's building scope
    # (the ledger carries a direct building); oversight roles see all.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    chosen = ledger_filters.get("building")
    if restrict:
        if not allowed or (chosen and chosen not in allowed):
            return columns, []
        if not chosen:
            ledger_filters["building"] = ["in", allowed]

    ledger_rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=ledger_filters,
        fields=["cleaning_log", "building", "posting_date", "cleaned"],
        limit_page_length=0,
    )

    # Aggregate the immutable per-room facts up to one row per source log.
    from collections import defaultdict
    log_total = defaultdict(int)
    log_cleaned = defaultdict(int)
    log_meta = {}
    for row in ledger_rows:
        log = row.cleaning_log
        log_total[log] += 1
        if row.cleaned:
            log_cleaned[log] += 1
        # The first row seen pins the log's building/date; all rows of a log share them.
        log_meta.setdefault(log, {"building": row.building, "cleaning_date": row.posting_date})

    log_names = list(log_total.keys())
    if not log_names:
        return columns, []

    # [#4f0bon] Best-effort supervisory enrichment from the live Cleaning Log.
    # These are review-state fields, not posted facts; a log dropped/cancelled
    # since posting simply yields blanks (its compliance fact still stands).
    enrich = {}
    log_meta_rows = frappe.get_all(
        "Cleaning Log",
        filters={"name": ["in", log_names]},
        fields=[
            "name", "cleaner_type", "cleaner_employee", "cleaner_name",
            "supervisor_approved", "supervisor_rating", "missed_cleaning",
            "missed_reason", "rework_required", "scheduled_task_instance",
        ],
    )
    enrich = {r.name: r for r in log_meta_rows}

    all_cleaner_employees = list({r.cleaner_employee for r in log_meta_rows if r.cleaner_employee})
    employee_name_map = {}
    if all_cleaner_employees:
        emp_rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", all_cleaner_employees]},
            fields=["name", "employee_name"],
        )
        employee_name_map = {e.name: e.employee_name for e in emp_rows}

    data = []
    for log in log_names:
        total = log_total[log]
        cleaned = log_cleaned[log]
        pct = (cleaned / total * 100) if total else 0.0

        meta = enrich.get(log)
        cleaner_label = ""
        if meta:
            cleaner_label = meta.cleaner_name or ""
            if meta.cleaner_employee:
                cleaner_label = employee_name_map.get(meta.cleaner_employee) or meta.cleaner_employee

        data.append({
            "name": log,
            "cleaning_date": log_meta[log]["cleaning_date"],
            "building": log_meta[log]["building"],
            "cleaner_type": (meta.cleaner_type if meta else "") or "",
            "cleaner": cleaner_label,
            "rooms_total": total,
            "rooms_cleaned": cleaned,
            "compliance_pct": round(pct, 1),
            "supervisor_approved": (meta.supervisor_approved if meta else 0),
            "supervisor_rating": (meta.supervisor_rating if meta else "") or "",
            "missed_cleaning": (meta.missed_cleaning if meta else 0),
            "rework_required": (meta.rework_required if meta else 0),
            "missed_reason": (meta.missed_reason if meta else "") or "",
            "scheduled_task_instance": (meta.scheduled_task_instance if meta else "") or "",
        })

    data.sort(key=lambda r: (str(r["cleaning_date"] or ""), r["building"] or ""), reverse=True)

    return columns, data
