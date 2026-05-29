"""Seed the native Salis Dashboards (charts + number cards) as data records.

Mirrors ``habitat/dashboard_seed.py``: Frappe does not reliably auto-sync
standalone is_standard Dashboard / Dashboard Chart / Number Card fixtures on
migrate, so they are created idempotently here. This module is the
``after_migrate`` entrypoint for the Salis fleet module and builds three
role dashboards: Fleet Manager, Fleet Supervisor, Finance Manager.

Idempotency / safety contract (mirrors Habitat):
- Every chart and card is upserted by name: a re-run updates in place and never
  duplicates.
- Every reference is existence-guarded — a missing Dashboard Chart / Number Card
  is skipped, never appended to a Dashboard, so the seed can never raise a
  LinkValidationError (which previously broke patches and opened GitHub issues —
  see memory `feedback_patches`).
- Each upsert (charts, cards, every dashboard) is wrapped in its own try/except.
  If the referenced DocType does not exist (module partially installed) the
  failure is rolled back and logged via ``frappe.log_error`` — it never aborts
  the migrate or the surrounding Habitat seed.

Real Salis DocTypes / fieldnames used here are verified against
``salis/doctype/*/*.json``. Notably the alert DocType is named **Operations
Alert** (not "Salis Operations Alert") and its ``status`` options are
Open|Acknowledged|Resolved.
"""

import json

import frappe

MODULE = "Salis"


# --------------------------------------------------------------------------- #
# Low-level idempotent record builders
# --------------------------------------------------------------------------- #
def _f(filters):
    """Serialize a python filter list to the filters_json string Frappe expects."""
    return json.dumps(filters)


def _upsert_chart(spec):
    """Create/update one Dashboard Chart by name. Existence-guarded on the
    target document_type so a missing DocType is skipped, not fatal."""
    name = spec["name"]
    doctype = spec["document_type"]
    try:
        if not frappe.db.exists("DocType", doctype):
            return  # source DocType not installed yet — skip silently
        values = {
            "doctype": "Dashboard Chart",
            "name": name,
            "chart_name": name,
            "module": MODULE,
            "is_public": 1,
            "is_standard": 0,
            "use_report_chart": 0,
            "number_of_groups": 0,
            "filters_json": _f(spec.get("filters", [])),
            "type": spec.get("type", "Bar"),
            "document_type": doctype,
            "chart_type": spec.get("chart_type", "Count"),
            "timeseries": 1 if spec.get("timeseries") else 0,
        }
        if spec.get("timeseries"):
            values["based_on"] = spec["based_on"]
            values["time_interval"] = spec.get("time_interval", "Monthly")
            values["timespan"] = spec.get("timespan", "Last Year")
        if spec.get("group_by_based_on"):
            values["group_by_based_on"] = spec["group_by_based_on"]
            values["group_by_type"] = spec.get("group_by_type", "Count")
        if spec.get("aggregate_function_based_on"):
            values["aggregate_function_based_on"] = spec["aggregate_function_based_on"]
        if spec.get("currency"):
            values["currency"] = spec["currency"]

        if frappe.db.exists("Dashboard Chart", name):
            doc = frappe.get_doc("Dashboard Chart", name)
            doc.update({k: v for k, v in values.items()
                        if k not in ("doctype", "name")})
            doc.save(ignore_permissions=True)  # audit-ok
        else:
            frappe.get_doc(values).insert(ignore_permissions=True)  # audit-ok
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Salis seed chart failed: {name}")


def _upsert_card(spec):
    """Create/update one Number Card by name. Existence-guarded on document_type."""
    name = spec["name"]
    doctype = spec["document_type"]
    try:
        if not frappe.db.exists("DocType", doctype):
            return  # source DocType not installed yet — skip silently
        function = spec.get("function", "Count")
        values = {
            "doctype": "Number Card",
            "name": name,
            "label": name,
            "module": MODULE,
            "is_public": 1,
            "is_standard": 0,
            "type": "Document Type",
            "document_type": doctype,
            "function": function,
            "filters_json": _f(spec.get("filters", [])),
            "show_percentage_stats": 1,
            "stats_time_interval": "Daily",
        }
        # Relative-date conditions (e.g. "< today") cannot live in static
        # filters_json — Frappe evaluates them from dynamic_filters_json, where
        # the value is a JS expression eval'd client-side.
        if spec.get("dynamic_filters"):
            values["dynamic_filters_json"] = _f(spec["dynamic_filters"])
        if function == "Sum":
            values["aggregate_function_based_on"] = spec["aggregate_function_based_on"]
            values["report_function"] = "Sum"
            values["show_percentage_stats"] = 0
        if spec.get("currency"):
            values["currency"] = spec["currency"]

        if frappe.db.exists("Number Card", name):
            doc = frappe.get_doc("Number Card", name)
            doc.update({k: v for k, v in values.items()
                        if k not in ("doctype", "name")})
            doc.save(ignore_permissions=True)  # audit-ok
        else:
            frappe.get_doc(values).insert(ignore_permissions=True)  # audit-ok
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Salis seed card failed: {name}")


def _existing_charts(charts):
    """[(chart_name, width)] -> child rows for charts that actually exist."""
    return [{"chart": n, "width": w} for n, w in charts
            if frappe.db.exists("Dashboard Chart", n)]


def _existing_cards(cards):
    return [{"card": c} for c in cards if frappe.db.exists("Number Card", c)]


def _upsert_dashboard(name, charts, cards):
    """Create/update one Dashboard, linking only charts/cards that exist."""
    try:
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
                                  "module": MODULE, "is_default": 0, "is_standard": 0})
        for ch in chart_rows:
            doc.append("charts", ch)
        for cd in card_rows:
            doc.append("cards", cd)
        if doc.is_new():
            doc.insert(ignore_permissions=True)  # audit-ok
        else:
            doc.save(ignore_permissions=True)  # audit-ok
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Salis seed dashboard failed: {name}")


# --------------------------------------------------------------------------- #
# Chart + card specifications (real DocTypes / fieldnames)
# --------------------------------------------------------------------------- #
_CHARTS = [
    # --- Fleet Manager ---
    {"name": "Vehicles by Status", "document_type": "Salis Vehicle", "type": "Donut",
     "chart_type": "Group By", "group_by_based_on": "status"},
    {"name": "Vehicles by Ownership", "document_type": "Salis Vehicle", "type": "Pie",
     "chart_type": "Group By", "group_by_based_on": "ownership"},
    {"name": "Vehicles by Category", "document_type": "Salis Vehicle", "type": "Bar",
     "chart_type": "Group By", "group_by_based_on": "vehicle_category"},
    {"name": "Active Assignments Over Time", "document_type": "Vehicle Assignment",
     "type": "Line", "chart_type": "Count", "timeseries": True, "based_on": "start_date",
     "time_interval": "Monthly",
     "filters": [["Vehicle Assignment", "docstatus", "=", 1]]},
    {"name": "Fuel Cost Trend", "document_type": "Fuel Request", "type": "Line",
     "chart_type": "Sum", "timeseries": True, "based_on": "request_date",
     "time_interval": "Monthly", "aggregate_function_based_on": "amount", "currency": "SAR",
     "filters": [["Fuel Request", "status", "=", "Done"]]},

    # --- Fleet Supervisor ---
    {"name": "Fuel Requests by Status", "document_type": "Fuel Request", "type": "Donut",
     "chart_type": "Group By", "group_by_based_on": "status"},
    {"name": "Driver Attendance Today by Status", "document_type": "Driver Attendance",
     "type": "Bar", "chart_type": "Group By", "group_by_based_on": "status",
     "filters": [["Driver Attendance", "attendance_date", "Timespan", "today"]]},
    {"name": "Support Tickets by Status", "document_type": "Support Ticket", "type": "Donut",
     "chart_type": "Group By", "group_by_based_on": "status"},
    {"name": "Dispatch Trips by Status", "document_type": "Dispatch Trip", "type": "Donut",
     "chart_type": "Group By", "group_by_based_on": "status"},

    # --- Finance Manager ---
    {"name": "Fuel Cost by Month", "document_type": "Fuel Request", "type": "Bar",
     "chart_type": "Sum", "timeseries": True, "based_on": "request_date",
     "time_interval": "Monthly", "aggregate_function_based_on": "amount", "currency": "SAR",
     "filters": [["Fuel Request", "status", "=", "Done"]]},
    {"name": "Fuel Cost by Platform", "document_type": "Fuel Request", "type": "Pie",
     "chart_type": "Group By", "group_by_based_on": "fuel_platform",
     "group_by_type": "Sum", "aggregate_function_based_on": "amount", "currency": "SAR",
     "filters": [["Fuel Request", "status", "=", "Done"]]},
    # "Fuel Requests by Status" reused from Fleet Supervisor (same chart record)
    {"name": "Topups by Status", "document_type": "Fuel Request", "type": "Bar",
     "chart_type": "Group By", "group_by_based_on": "status",
     "filters": [["Fuel Request", "request_type", "=", "Top-up"]]},
]

_CARDS = [
    # --- Fleet Manager ---
    {"name": "Active Vehicles", "document_type": "Salis Vehicle",
     "filters": [["Salis Vehicle", "status", "=", "Active"]]},
    {"name": "Vehicles Under Maintenance", "document_type": "Salis Vehicle",
     "filters": [["Salis Vehicle", "status", "=", "Under Maintenance"]]},
    {"name": "Stopped Vehicles", "document_type": "Salis Vehicle",
     "filters": [["Salis Vehicle", "status", "=", "Stopped"]]},
    {"name": "Owned Vehicles", "document_type": "Salis Vehicle",
     "filters": [["Salis Vehicle", "ownership", "=", "Owned"]]},
    {"name": "Rented Vehicles", "document_type": "Salis Vehicle",
     "filters": [["Salis Vehicle", "ownership", "=", "Rented"]]},
    {"name": "Active Vehicle Assignments", "document_type": "Vehicle Assignment",
     "filters": [["Vehicle Assignment", "status", "=", "Active"],
                 ["Vehicle Assignment", "docstatus", "=", 1]]},
    # "Vehicles Without Active Assignment" — pure derived (needs a Query/Report card);
    # no count-filter equivalent exists, so it is intentionally omitted to keep the
    # seed crash-free. Flagged for a report-card task.

    # --- Fleet Supervisor ---
    {"name": "Pending Fuel Requests", "document_type": "Fuel Request",
     "filters": [["Fuel Request", "status", "=", "Pending"],
                 ["Fuel Request", "docstatus", "=", 1]]},
    {"name": "Drivers Present Today", "document_type": "Driver Attendance",
     "filters": [["Driver Attendance", "status", "=", "Present"],
                 ["Driver Attendance", "attendance_date", "Timespan", "today"],
                 ["Driver Attendance", "docstatus", "=", 1]]},
    {"name": "Drivers Absent Today", "document_type": "Driver Attendance",
     "filters": [["Driver Attendance", "status", "=", "Absent"],
                 ["Driver Attendance", "attendance_date", "Timespan", "today"],
                 ["Driver Attendance", "docstatus", "=", 1]]},
    {"name": "Open Support Tickets", "document_type": "Support Ticket",
     "filters": [["Support Ticket", "status", "in", ["New", "In Progress", "Waiting"]],
                 ["Support Ticket", "docstatus", "=", 1]]},
    {"name": "Urgent Support Tickets", "document_type": "Support Ticket",
     "filters": [["Support Ticket", "priority", "=", "Urgent"],
                 ["Support Ticket", "status", "!=", "Closed"]]},
    # "Vehicles Needing Handover" — derived comparison, no count-filter equivalent; omitted.
    {"name": "Open Operations Alerts", "document_type": "Operations Alert",
     "filters": [["Operations Alert", "status", "=", "Open"]]},

    # --- Finance Manager ---
    {"name": "Fuel Cost This Month", "document_type": "Fuel Request", "function": "Sum",
     "aggregate_function_based_on": "amount", "currency": "SAR",
     "filters": [["Fuel Request", "status", "=", "Done"],
                 ["Fuel Request", "request_date", "Timespan", "this month"]]},
    {"name": "Approved Fuel Awaiting Fulfilment", "document_type": "Fuel Request",
     "filters": [["Fuel Request", "status", "=", "Approved"],
                 ["Fuel Request", "docstatus", "=", 1]]},
    {"name": "Unreverted Temporary Topups", "document_type": "Fuel Request",
     "filters": [["Fuel Request", "request_type", "=", "Top-up"],
                 ["Fuel Request", "is_temporary", "=", 1],
                 ["Fuel Request", "reverted", "=", 0],
                 ["Fuel Request", "status", "!=", "Cancelled"]]},
    {"name": "Overdue Temporary Topups", "document_type": "Fuel Request",
     "filters": [["Fuel Request", "request_type", "=", "Top-up"],
                 ["Fuel Request", "is_temporary", "=", 1],
                 ["Fuel Request", "reverted", "=", 0]],
     # revert_due_date < today is dynamic — evaluated from dynamic_filters_json.
     "dynamic_filters": [["Fuel Request", "revert_due_date", "<",
                          "frappe.datetime.get_today()"]]},
    {"name": "Failed Fuel Requests", "document_type": "Fuel Request",
     "filters": [["Fuel Request", "status", "=", "Failed"]]},
]


def _seed_records():
    """Create/update every chart and card before linking them into dashboards."""
    for spec in _CHARTS:
        _upsert_chart(spec)
    for spec in _CARDS:
        _upsert_card(spec)
    frappe.db.commit()


# --------------------------------------------------------------------------- #
# Role dashboards
# --------------------------------------------------------------------------- #
def seed_fleet_manager_dashboard():
    _upsert_dashboard(
        "Fleet Manager Dashboard",
        charts=[("Vehicles by Status", "Half"), ("Vehicles by Ownership", "Half"),
                ("Vehicles by Category", "Half"), ("Active Assignments Over Time", "Half"),
                ("Fuel Cost Trend", "Full")],
        cards=["Active Vehicles", "Vehicles Under Maintenance", "Stopped Vehicles",
               "Owned Vehicles", "Rented Vehicles", "Active Vehicle Assignments"],
    )


def seed_fleet_supervisor_dashboard():
    _upsert_dashboard(
        "Fleet Supervisor Dashboard",
        charts=[("Fuel Requests by Status", "Half"), ("Driver Attendance Today by Status", "Half"),
                ("Support Tickets by Status", "Half"), ("Dispatch Trips by Status", "Full")],
        cards=["Pending Fuel Requests", "Drivers Present Today", "Drivers Absent Today",
               "Open Support Tickets", "Urgent Support Tickets", "Open Operations Alerts"],
    )


def seed_finance_manager_dashboard():
    # NOTE: Habitat already owns a Dashboard named "Finance Manager Dashboard"
    # (habitat/dashboard_seed.py + costs.json link). Both seeds run on
    # after_migrate, so reusing that name would clobber Habitat's charts/cards.
    # Namespaced to "Salis Finance Manager Dashboard" to keep both intact.
    _upsert_dashboard(
        "Salis Finance Manager Dashboard",
        charts=[("Fuel Cost by Month", "Half"), ("Fuel Cost by Platform", "Half"),
                ("Fuel Requests by Status", "Half"), ("Topups by Status", "Full")],
        cards=["Fuel Cost This Month", "Approved Fuel Awaiting Fulfilment",
               "Unreverted Temporary Topups", "Overdue Temporary Topups",
               "Failed Fuel Requests"],
    )


# --------------------------------------------------------------------------- #
# Movement-department division dashboards (Workers Transport vs Representatives)
# --------------------------------------------------------------------------- #
# These two dashboards reflect the Movement Department's two divisions. Their
# charts and number cards ship as committed JSON fixtures under
# salis/dashboard_chart/ and salis/number_card/ (imported by bench migrate
# before this after_migrate seed runs), so the seed only has to *link* them.
# As with every dashboard here, _upsert_dashboard links only the charts/cards
# that actually exist, so a partial install never raises LinkValidationError.
def seed_workers_transport_dashboard():
    # Charts/cards suffixed "(NEW)" are produced by the Salis cards-charts-depth
    # fixtures (salis/dashboard_chart/, salis/number_card/) and referenced here by
    # name only. _upsert_dashboard links solely the ones that actually exist, so a
    # not-yet-synced fixture is skipped, never a LinkValidationError. The division
    # reports (Worker Transport Plan, Transport Fulfilment SLA, Driver Attendance
    # Summary) are surfaced as report links in the Salis Workers Transport
    # workspace — Dashboards in this app hold only charts + number cards.
    _upsert_dashboard(
        "Salis - Workers Transport",
        charts=[("Workers Requests by Status", "Half"),
                ("Workers Transport Over Time", "Half"),
                ("Transport Requests by Service Line", "Half")],  # NEW
        cards=["Workers Requests Open", "Open Transport Requests",
               "Inter-City Relocations This Month",
               "Large Worker Moves Pending Escalation",
               "Workers Transport Fulfilled This Month",  # NEW
               "Transport SLA Breaches Open"],             # NEW
    )


def seed_representatives_fleet_dashboard():
    # See seed_workers_transport_dashboard: "(NEW)" tiles are fixture-backed and
    # referenced by name only; missing ones are skipped by the existence guard.
    # Division reports (Salis Fleet Register, Vehicle Utilisation, Vehicle/Driver
    # Clearance registers, rental reports) are surfaced as report links in the
    # Salis Representatives Fleet / Rentals & Costs / Compliance & Drivers
    # workspaces.
    _upsert_dashboard(
        "Salis - Representatives Fleet",
        charts=[("Vehicles by Status", "Half"), ("Dispatch Trips by Status", "Half"),
                ("Fuel Spend by Platform", "Half"), ("Fuel Spend Trend", "Half"),
                ("Active Vehicles by Category", "Half"),    # NEW
                ("Fuel Claim Variance by Month", "Half"),   # NEW
                ("Rental Accrual Trend", "Full")],          # NEW
        cards=["Active Vehicles", "Vehicles Under Maintenance",
               "Expiring Vehicle Compliance", "Pending Fuel Requests",
               "Fuel Spend This Month", "Open Fuel Exception Cases",
               "Rental Accrual This Month", "Blocked Driver Clearances",
               "Representatives Transport Requests Open",        # NEW
               "Representatives Transport Fulfilled This Month",  # NEW
               "Disputed Rental Settlements",                    # NEW
               "Overdue Rental Settlements",                     # NEW
               "Cost Recovery Aging Backlog"],                   # NEW
    )


def seed_salis_dashboards(*args, **kwargs):
    """after_migrate entrypoint: build Salis charts/cards, then the role dashboards.

    Runs after charts/cards are synced so dashboards populate reliably
    (after_install is too early — the charts don't exist yet). Each step is
    independently guarded, so a partially installed module never aborts migrate
    or the Habitat seed that runs alongside it.
    """
    _seed_records()
    seed_fleet_manager_dashboard()
    seed_fleet_supervisor_dashboard()
    seed_finance_manager_dashboard()
    seed_workers_transport_dashboard()
    seed_representatives_fleet_dashboard()
    frappe.db.commit()
