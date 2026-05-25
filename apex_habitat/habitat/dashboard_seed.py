"""Seed the native Habitat Dashboards as data records.

Frappe does not reliably auto-sync a standalone is_standard Dashboard fixture on
migrate, so we create them idempotently here. These dashboards re-home the charts
and number cards that were stripped from the navigation-first Workspaces, and add
per-role dashboards (visible via the role-restricted Workspace each is linked from).

Every chart/card reference is existence-guarded: a missing record is skipped, never
appended, so the seed can never raise a LinkValidationError (which previously broke
the patch and opened GitHub issues).
"""

import frappe


def _existing_charts(charts):
    """[(chart_name, width)] -> child rows for charts that actually exist."""
    rows = []
    for name, width in charts:
        if frappe.db.exists("Dashboard Chart", name):
            rows.append({"chart": name, "width": width})
    return rows


def _existing_cards(cards):
    return [{"card": c} for c in cards if frappe.db.exists("Number Card", c)]


def _upsert_dashboard(name, charts, cards):
    chart_rows = _existing_charts(charts)
    card_rows = _existing_cards(cards)
    if not chart_rows and not card_rows:
        return  # nothing valid to show — don't create an empty dashboard
    if frappe.db.exists("Dashboard", name):
        doc = frappe.get_doc("Dashboard", name)
        doc.set("charts", [])
        doc.set("cards", [])
    else:
        doc = frappe.get_doc({"doctype": "Dashboard", "dashboard_name": name,
                              "module": "Habitat", "is_default": 0, "is_standard": 0})
    for ch in chart_rows:
        doc.append("charts", ch)
    for cd in card_rows:
        doc.append("cards", cd)
    doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)  # audit-ok


def seed_habitat_dashboard():
    """Operations overview dashboard (linked from the Habitat workspace)."""
    _upsert_dashboard(
        "Habitat Dashboard",
        charts=[("Beds by Status", "Half"), ("Occupancy Percent Trend", "Half"),
                ("Maintenance Requests by Status", "Half"), ("Scheduled Task Instances by Status", "Half"),
                ("Task Completions Over Time", "Full")],
        cards=["Open Maintenance Requests", "Overdue Scheduled Tasks", "Licenses Expiring Soon", "Vacant Beds"],
    )
    frappe.db.commit()


def seed_all_dashboards(*args, **kwargs):
    """after_migrate entrypoint: runs once charts/cards are synced, so dashboards
    populate reliably (after_install is too early — the charts don't exist yet)."""
    seed_habitat_dashboard()
    seed_role_dashboards()


def seed_role_dashboards():
    """Per-role dashboards. Each re-homes the workspace charts/cards for its audience
    and is reachable from that role's (role-restricted) Workspace."""
    _upsert_dashboard(
        "Accommodation Manager Dashboard",
        charts=[("Beds by Status", "Half"), ("Occupancy Percent Trend", "Half"),
                ("Accommodation Leases by Status", "Full")],
        cards=["Occupied Beds", "Vacant Beds", "Pending Accommodation Checkouts", "Active Accommodation Assignments"],
    )
    _upsert_dashboard(
        "Resident Supervisor Dashboard",
        charts=[("Maintenance Requests by Status", "Half"), ("Maintenance Requests by Priority", "Half"),
                ("Scheduled Task Instances by Status", "Full")],
        cards=["Open Maintenance Requests", "Overdue Scheduled Tasks", "Open Custody Issues", "Tasks Due Today"],
    )
    _upsert_dashboard(
        "Finance Manager Dashboard",
        charts=[("Ledger Cost by Type", "Half"), ("Utility Bills by Status", "Half"),
                ("Subcontractor Service Orders by Status", "Full")],
        cards=["Active Leases", "Utility Bills Under Review", "Ledger Cost This Month", "Supplier-Billed Cost This Month"],
    )
    _upsert_dashboard(
        "Internal Auditor Dashboard",
        charts=[("Building Licenses by Status", "Half"), ("Safety Task Executions by Result", "Half"),
                ("Audit Remediation Plans by Status", "Full")],
        cards=["Open Audit Remediation Plans", "Overdue Audit Remediation Plans", "Licenses Expiring Soon", "Safety Inspections Recorded"],
    )
    frappe.db.commit()
