"""Seed the Salis Movement (operational KPI) dashboard as data records.

Standalone companion to ``salis/dashboard_seed.py``. It builds one
**Movement Operations Dashboard** (charts + number cards) that surface the
operational KPIs for the Movement domain:

- daily transport request fulfilment rate
- fuel claim submission accuracy
- vehicle handover documentation completeness
- inter-city workforce transport plan fulfilment
- vehicle utilisation

Design reference:
``internal design notes``
(Part 3 — Background Engines). Several charts/cards reference the *new* engine
DocTypes that may not be migrated yet on a given site:

- Trip Fulfilment Ledger
- Fuel Consumption Ledger
- Rental Accrual Ledger
- Vehicle Utilisation Snapshot

Idempotency / safety contract (mirrors ``salis/dashboard_seed.py``):
- Every chart and card is upserted by name; a re-run updates in place, never
  duplicates.
- Each upsert is existence-guarded on its source DocType via
  ``frappe.db.exists("DocType", X)`` — a not-yet-migrated engine DocType is
  skipped silently, never fatal.
- Each upsert is wrapped in its own try/except with ``frappe.db.rollback()``
  + ``frappe.log_error`` so a partially installed module never aborts migrate
  or the surrounding Salis/Habitat seeds.
- The dashboard links only charts/cards that actually got created, so it can
  never raise a LinkValidationError.

This module does NOT touch ``salis/dashboard_seed.py``. The orchestrator wires
``apex_habitat.salis.movement_dashboard_seed.seed_movement_dashboards`` into
``after_migrate`` separately.

Fieldnames are verified against ``salis/doctype/*/*.json``:
- Dispatch Trip.status options: Planned|Dispatched|Completed|Cancelled; date
  field ``trip_date``.
- Transport Request.status options: New|Validated|Approved|Scheduled|Fulfilled|
  Rejected|Cancelled; ``request_type`` includes "Inter-City Relocation";
  ``pickup_datetime`` is the schedule date; ``is_cross_region`` flags inter-city.
- Fuel Exception Case.status options include "Open".
The engine ledger fieldnames (trip_date / litres / period_month / amount /
rental_office / utilisation_pct) follow the design spec; if an engine DocType
is absent the whole spec is skipped by the existence guard.
"""

import json

import frappe

MODULE = "Salis"
DASHBOARD_NAME = "Movement Operations Dashboard"


# --------------------------------------------------------------------------- #
# Low-level idempotent record builders
# --------------------------------------------------------------------------- #
def _f(filters):
    """Serialize a python filter list to the filters_json string Frappe expects."""
    return json.dumps(filters)


def _upsert_chart(spec):
    """Create/update one Dashboard Chart by name. Existence-guarded on the
    target document_type so a missing (engine) DocType is skipped, not fatal."""
    name = spec["name"]
    doctype = spec["document_type"]
    try:
        if not frappe.db.exists("DocType", doctype):
            return  # source/engine DocType not migrated yet — skip silently
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
        frappe.log_error(frappe.get_traceback(),
                         f"Salis movement seed chart failed: {name}")


def _upsert_card(spec):
    """Create/update one Number Card by name. Existence-guarded on document_type."""
    name = spec["name"]
    doctype = spec["document_type"]
    try:
        if not frappe.db.exists("DocType", doctype):
            return  # source/engine DocType not migrated yet — skip silently
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
        # Relative-date conditions cannot live in static filters_json — Frappe
        # evaluates them from dynamic_filters_json (a JS expression).
        if spec.get("dynamic_filters"):
            values["dynamic_filters_json"] = _f(spec["dynamic_filters"])
        if function in ("Sum", "Average"):
            values["aggregate_function_based_on"] = spec["aggregate_function_based_on"]
            values["report_function"] = function
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
        frappe.log_error(frappe.get_traceback(),
                         f"Salis movement seed card failed: {name}")


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
        frappe.log_error(frappe.get_traceback(),
                         f"Salis movement seed dashboard failed: {name}")


# --------------------------------------------------------------------------- #
# Chart + card specifications (verified fieldnames; engine DocTypes guarded)
# --------------------------------------------------------------------------- #
_CHARTS = [
    # Trips by Status — Dispatch Trip (exists).
    {"name": "Movement Trips by Status", "document_type": "Dispatch Trip",
     "type": "Donut", "chart_type": "Group By", "group_by_based_on": "status"},
    # Trip Fulfilment Over Time — engine ledger (NEW; guarded).
    {"name": "Trip Fulfilment Over Time", "document_type": "Trip Fulfilment Ledger",
     "type": "Line", "chart_type": "Count", "timeseries": True,
     "based_on": "trip_date", "time_interval": "Daily", "timespan": "Last Month"},
    # Fuel Consumption by Month — engine ledger (NEW; guarded). Sum litres by period.
    {"name": "Fuel Consumption by Month", "document_type": "Fuel Consumption Ledger",
     "type": "Bar", "chart_type": "Sum", "timeseries": True,
     "based_on": "period_month", "time_interval": "Monthly",
     "aggregate_function_based_on": "litres"},
    # Rental Accrual by Office — engine ledger (NEW; guarded). Sum amount by office.
    {"name": "Rental Accrual by Office", "document_type": "Rental Accrual Ledger",
     "type": "Pie", "chart_type": "Group By", "group_by_based_on": "rental_office",
     "group_by_type": "Sum", "aggregate_function_based_on": "amount",
     "currency": "SAR"},
    # Vehicle Utilisation — engine snapshot (NEW; guarded). Average utilisation_pct.
    {"name": "Vehicle Utilisation", "document_type": "Vehicle Utilisation Snapshot",
     "type": "Bar", "chart_type": "Average",
     "aggregate_function_based_on": "utilisation_pct"},
]

_CARDS = [
    # Completed Trips today — Dispatch Trip status "Completed".
    {"name": "Completed Trips Today", "document_type": "Dispatch Trip",
     "filters": [["Dispatch Trip", "status", "=", "Completed"],
                 ["Dispatch Trip", "trip_date", "Timespan", "today"]]},
    # Completed Trips this month.
    {"name": "Completed Trips This Month", "document_type": "Dispatch Trip",
     "filters": [["Dispatch Trip", "status", "=", "Completed"],
                 ["Dispatch Trip", "trip_date", "Timespan", "this month"]]},
    # Pending Transport Requests — Transport Request status "New".
    {"name": "Pending Transport Requests", "document_type": "Transport Request",
     "filters": [["Transport Request", "status", "=", "New"]]},
    # Open Fuel Exception Cases — Fuel Exception Case status "Open".
    {"name": "Open Fuel Exception Cases", "document_type": "Fuel Exception Case",
     "filters": [["Fuel Exception Case", "status", "=", "Open"]]},
    # Rental Accrual This Month (Sum) — engine ledger (NEW; guarded).
    {"name": "Rental Accrual This Month", "document_type": "Rental Accrual Ledger",
     "function": "Sum", "aggregate_function_based_on": "amount", "currency": "SAR",
     "filters": [["Rental Accrual Ledger", "period_month", "Timespan", "this month"]]},
    # Vehicles Tracked — distinct vehicles in the utilisation snapshot (NEW; guarded).
    {"name": "Vehicles Tracked", "document_type": "Vehicle Utilisation Snapshot"},
    # Inter-City Requests This Month — Transport Request, inter-city relocation.
    {"name": "Inter-City Requests This Month", "document_type": "Transport Request",
     "filters": [["Transport Request", "request_type", "=", "Inter-City Relocation"],
                 ["Transport Request", "pickup_datetime", "Timespan", "this month"]]},
]


def _seed_records():
    """Create/update every chart and card before linking them into the dashboard."""
    for spec in _CHARTS:
        _upsert_chart(spec)
    for spec in _CARDS:
        _upsert_card(spec)
    frappe.db.commit()


# --------------------------------------------------------------------------- #
# Movement KPI dashboard
# --------------------------------------------------------------------------- #
def seed_movement_dashboards(*args, **kwargs):
    """after_migrate entrypoint: build Movement charts/cards, then the dashboard.

    Each chart/card/dashboard step is independently guarded, so a site where the
    Movement engine DocTypes (Trip Fulfilment Ledger, Fuel Consumption Ledger,
    Rental Accrual Ledger, Vehicle Utilisation Snapshot) are not yet migrated
    simply seeds fewer tiles — it never aborts migrate or other seeds.
    """
    _seed_records()
    _upsert_dashboard(
        DASHBOARD_NAME,
        charts=[("Movement Trips by Status", "Half"),
                ("Trip Fulfilment Over Time", "Half"),
                ("Fuel Consumption by Month", "Half"),
                ("Rental Accrual by Office", "Half"),
                ("Vehicle Utilisation", "Full")],
        cards=["Completed Trips Today", "Completed Trips This Month",
               "Pending Transport Requests", "Open Fuel Exception Cases",
               "Rental Accrual This Month", "Vehicles Tracked",
               "Inter-City Requests This Month"],
    )
    frappe.db.commit()
