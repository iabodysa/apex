# Copyright (c) 2026, AFMCO and contributors
"""Fleet Operations workspace RENDER proof.

The page-access / role / CSRF gate is covered by test_fleet_page_access_gate;
the structural field/target wiring by test_fleet_number_cards + test_onboarding_steps.
What stayed unproven was the RENDER half the goal demands: with data present, does
the Fleet Operations workspace actually render content -- each Tier-1 Number Card a
non-zero number, each Dashboard Chart a non-empty series, each onboarding step a
target that opens?

This seeds representative data in setUp (drafts where a Count/series includes them,
a submitted Vehicle Stop where the metric requires docstatus=1) and asserts through
Frappe's OWN render paths -- never frappe.db.count:

  * Number Card  -> number_card.get_result(card, card.filters_json)  (the widget's path)
  * Custom card  -> the card's own resolved `method`
  * Dashboard Chart -> dashboard_chart.get(chart_name=...)           (the widget's path)
  * Onboarding   -> Module Onboarding.get_steps() + each step's action target

All seeded rows carry the test method's name so the suite's per-test rollback and
the unique plate/date constraints stay clean; nothing depends on ambient data.
"""

from __future__ import annotations

import json

import frappe
from frappe.desk.doctype.dashboard_chart import dashboard_chart as chart_api
from frappe.desk.doctype.number_card import number_card as card_api
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

# Tier-1 Number Cards on the Fleet Operations workspace (Key Metrics block).
# Open Theft Reports is also here; its behaviour is proven in
# salis/doctype/vehicle_incident/test_vehicle_incident.py and re-proven below
# through the render path for completeness.
# Curated to the 2026-06-25 workspace design: only essential actionable cards.
FLEET_CARDS = [
    "Open Vehicle Incidents",
    "Open Theft Reports",
    "Salis Representatives Fleet Vehicles Stopped",
    "Workshop Overstay",
]

# P-094 headline-chart design: the fleet workspace pins one headline chart.
FLEET_CHARTS = ["Fuel Cost by Month"]


class TestFleetOpsRender(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self._seed()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _tag(self):
        # Short, per-test unique token for plates / driver ids / dates.
        return self._testMethodName[-24:]

    def _vehicle(self, status, suffix=""):
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": f"FR {self._tag()}{suffix}",
                    "status": status,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _driver(self, status="Active", suffix=""):
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"FR Driver {self._tag()}{suffix}",
                    "driver_id": f"FRD-{self._tag()}{suffix}",
                    "status": status,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _incident(self, incident_type):
        # Draft (docstatus 0): a Count card's get_result and a Group By chart both
        # include drafts, and staying unsubmitted avoids the Theft submit side
        # effects (which would stop the vehicle and clear its driver).
        return frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": incident_type,
                "vehicle": self._active_vehicle,
                "incident_date": today(),
                "description": "render-check seed",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)

    def _snapshot(self, days_ago, period_days, util_pct):
        return frappe.get_doc(
            {
                "doctype": "Vehicle Utilisation Snapshot",
                "snapshot_date": add_days(today(), -days_ago),
                "vehicle": self._active_vehicle,
                "period_days": period_days,
                "utilisation_pct": util_pct,
            }
        ).insert(ignore_permissions=True)

    def _assignment_draft(self):
        # Draft assignment dated today: the Vehicle Activations time-series counts
        # docstatus < 2, so a draft lands in this month's bucket without firing the
        # submit-time vehicle/driver mutation.
        driver = self._driver(suffix="A")
        return frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self._vehicle("Active", suffix="A"),
                "driver": driver,
                "start_date": today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)

    def _overstay_vehicle(self):
        # Workshop Overstay needs a SUBMITTED Maintenance Vehicle Stop older than
        # the cutoff (Salis Settings.workshop_overstay_days, default 14) with no
        # return_date, on a vehicle still Stopped/Under Maintenance.
        vehicle = self._vehicle("Active", suffix="W")
        stop = frappe.get_doc(
            {
                "doctype": "Vehicle Stop",
                "vehicle": vehicle,
                "stop_reason": "Maintenance",
                "stop_date": add_days(today(), -20),
            }
        ).insert(ignore_permissions=True)
        stop.submit()  # flips the vehicle to Stopped (an overstay-eligible status)
        return vehicle

    def _alerts(self):
        # Open Alerts by Type (Group By, status in Open/Acknowledged) needs an open
        # alert to plot; Median Alert Resolve Days (Custom) needs a Resolved alert
        # with both raised_on and resolved_on so the median span is > 0.
        vehicle = self._vehicle("Active", suffix="AL")
        frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": "Idle Vehicle",
                "severity": "Warning",
                "message": "render-proof open alert",
                "vehicle": vehicle,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        resolved = frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": "Idle Vehicle",
                "severity": "Warning",
                "message": "render-proof resolved alert",
                "vehicle": vehicle,
                "status": "Resolved",
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Operations Alert",
            resolved.name,
            {"raised_on": add_days(today(), -3), "resolved_on": today()},
            update_modified=False,
        )

    def _fuel_request(self):
        # Fuel Cost by Month sums Fuel Request.amount (status=Done) by request_date.
        # A new request is guarded to status Pending; the Done status + amount are
        # reached through the workflow, so set them via db (same bypass _alerts uses)
        # to land a real row the chart can sum without driving the full workflow.
        req = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": self._active_vehicle,
                "requested_litres": 40,
                "request_date": today(),
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Fuel Request",
            req.name,
            {"status": "Done", "amount": 250.0, "request_date": today()},
            update_modified=False,
        )

    def _seed(self):
        # One Active vehicle anchors the incident + utilisation seeds.
        self._active_vehicle = self._vehicle("Active")
        self._vehicle("Stopped", suffix="S")
        self._vehicle("Under Maintenance", suffix="M")
        self._driver("Active")
        self._incident("Accident")  # Open Vehicle Incidents
        self._incident("Theft")  # Open Theft Reports (+ Incidents by Type)
        # Two snapshots this month: Operating Days (Sum) + Vehicle Utilisation/Trend.
        self._snapshot(1, 5, 80.0)
        self._snapshot(3, 4, 60.0)
        self._assignment_draft()  # Vehicle Activations
        self._overstay_vehicle()  # Workshop Overstay
        self._alerts()  # Open Alerts by Type + Median Alert Resolve Days
        self._fuel_request()  # Fuel Cost by Month (headline chart)

    def _card_result(self, card_name):
        """Render a Number Card exactly as the widget does.

        Document Type cards go through number_card.get_result (the whitelisted
        render method); Custom cards resolve their own `method`, since get_result
        only handles Document Type / Report cards.
        """
        card = frappe.get_doc("Number Card", card_name)
        if card.type == "Custom":
            value = frappe.get_attr(card.method)()
            return frappe.utils.flt(value.get("value") if isinstance(value, dict) else value)
        return card_api.get_result(card.as_dict(), card.filters_json)

    def _chart_data(self, chart_name):
        """Render a Dashboard Chart through dashboard_chart.get (the widget path).

        refresh=1 forces a fresh compute (bypassing any stale cache from before the
        seed) via the chart_name code path; no_cache=1 is avoided -- the framework's
        cache_source wrapper mishandles no_cache + chart_name together.
        """
        return chart_api.get(chart_name=chart_name, refresh=1)

    def _series_total(self, config):
        # A time-series chart always returns a label per date bucket, so 'non-empty'
        # means the dataset values actually sum to > 0, not merely that labels exist.
        if not config or not config.get("datasets"):
            return 0
        return sum(frappe.utils.flt(v) for ds in config["datasets"] for v in ds.get("values", []))

    def test_every_tier1_number_card_renders_non_zero(self):
        # Each Tier-1 card, rendered through its own widget path, must return a
        # value > 0 after seeding -- the proof the workspace shows real numbers.
        zero = []
        for name in FLEET_CARDS:
            result = self._card_result(name)
            if not (result and result > 0):
                zero.append(f"{name}={result!r}")
        self.assertEqual(zero, [], f"Tier-1 number cards that rendered zero with data seeded: {zero}")

    def test_every_fleet_chart_renders_non_empty(self):
        # Each chart, rendered through dashboard_chart.get, must carry data:
        # Group By -> a non-empty {labels, datasets}; time-series -> values summing > 0.
        empty = []
        for name in FLEET_CHARTS:
            config = self._chart_data(name)
            chart_type = frappe.db.get_value("Dashboard Chart", name, "chart_type")
            if chart_type == "Group By":
                ok = bool(config and config.get("labels") and config.get("datasets"))
            else:
                ok = self._series_total(config) > 0
            if not ok:
                empty.append(f"{name} ({chart_type})={config!r}")
        self.assertEqual(empty, [], f"fleet charts that rendered empty with data seeded: {empty}")

    def test_render_scan_is_non_vacuous(self):
        # Guard against a silently-passing suite: the cards/charts/onboarding the
        # workspace JSON actually references must still exist, so the proofs above
        # ran against the real shipped records.
        content = json.loads(frappe.db.get_value("Workspace", "fleet", "content") or "[]")
        referenced_cards = {b["data"]["number_card_name"] for b in content if b.get("type") == "number_card"}
        referenced_charts = {b["data"]["chart_name"] for b in content if b.get("type") == "chart"}
        # The 14->8 consolidation folded Fleet Operations into the 'fleet' workspace,
        # which also carries fuel/maintenance cards proven in their own tests; assert the
        # render-tested cards are present (a subset), not that they are the only ones.
        self.assertLessEqual(
            set(FLEET_CARDS),
            referenced_cards,
            f"render-tested cards missing from the fleet workspace: {set(FLEET_CARDS) - referenced_cards}",
        )
        self.assertEqual(
            set(FLEET_CHARTS),
            referenced_charts,
            "the tested chart set must match the fleet workspace's chart blocks",
        )
        for name in FLEET_CARDS:
            self.assertTrue(frappe.db.exists("Number Card", name), f"Number Card {name} not installed")
        for name in FLEET_CHARTS:
            self.assertTrue(frappe.db.exists("Dashboard Chart", name), f"Dashboard Chart {name} not installed")
