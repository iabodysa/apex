# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.report.accommodation_occupancy_summary.accommodation_occupancy_summary import execute as execute_occupancy
from apex_habitat.habitat.report.accommodation_cost_distribution.accommodation_cost_distribution import execute as execute_cost
from apex_habitat.habitat.report.lease_expiry_watchlist.lease_expiry_watchlist import execute as execute_lease
from apex_habitat.habitat.report.utility_variance_report.utility_variance_report import execute as execute_utility
from apex_habitat.habitat.report.custody_damage_register.custody_damage_register import execute as execute_custody
from apex_habitat.habitat.report.scheduled_task_compliance.scheduled_task_compliance import execute as execute_task
from apex_habitat.habitat.report.maintenance_backlog.maintenance_backlog import execute as execute_maintenance
from apex_habitat.habitat.report.maintenance_aging.maintenance_aging import execute as execute_maint_aging
from apex_habitat.habitat.report.accommodation_ledger_summary.accommodation_ledger_summary import execute as execute_ledger_summary
from apex_habitat.habitat.report.supplier_cost_recovery.supplier_cost_recovery import execute as execute_supplier
from apex_habitat.habitat.report.occupancy_trend.occupancy_trend import execute as execute_occ_trend
from apex_habitat.salis.report.movement_cost_summary.movement_cost_summary import execute as execute_mov_summary
from apex_habitat.salis.report.movement_cost_recovery_register.movement_cost_recovery_register import execute as execute_mov_recovery
from apex_habitat.salis.report.rental_settlement_register.rental_settlement_register import execute as execute_rental_settlement
from apex_habitat.salis.report.rental_variance_report.rental_variance_report import execute as execute_rental_variance
from apex_habitat.salis.report.salis_payment_register.salis_payment_register import execute as execute_payment
from apex_habitat.salis.report.fuel_reconciliation.fuel_reconciliation import execute as execute_fuel_recon
from apex_habitat.salis.report.cost_recovery_aging.cost_recovery_aging import execute as execute_cost_aging
from apex_habitat.salis.report.fuel_spend_by_vehicle.fuel_spend_by_vehicle import execute as execute_fuel_spend
from apex_habitat.salis.report.transport_fulfilment_sla.transport_fulfilment_sla import execute as execute_transport_sla


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestReports(ApexHabitatTestCase):
    """Smoke-test the report execute() entrypoints.

    These tests verify that each report's `execute()` returns a valid
    (columns, data[, message, chart]) shape without raising. They intentionally
    do not assert that data is non-empty for the shape tests, because in a fresh
    CI database there are no seeded transactional records. The dedicated
    project-filter test seeds its own records to prove the filter narrows.
    """

    def _assert_report_shape(self, result):
        self.assertIsInstance(result, tuple, "Report execute() must return a tuple.")
        self.assertGreaterEqual(len(result), 2, "Report execute() must return at least (columns, data).")
        columns, data = result[0], result[1]
        self.assertIsNotNone(columns, "Report columns must not be None.")
        self.assertIsInstance(columns, list)
        self.assertGreater(len(columns), 0, "Report must declare at least one column.")
        self.assertIsInstance(data, list, "Report data must be a list.")

    def _assert_chart_report(self, result):
        """A report that returns (columns, data, message, chart). The chart may be
        None when there is no data, but if present it must be a valid frappe chart
        dict: a type plus data.labels and at least one dataset with a values list of
        the same length as labels."""
        self._assert_report_shape(result)
        self.assertGreaterEqual(len(result), 4, "Chart report must return (columns, data, message, chart).")
        chart = result[3]
        data = result[1]
        if not data:
            self.assertIsNone(chart, "Chart must be None when the report has no rows.")
            return
        if chart is None:
            # Allowed: rows exist but none contribute to the chart (all-zero series, no dated rows).
            return
        self.assertIsInstance(chart, dict, "Chart must be a dict.")
        self.assertIn(chart.get("type"), ("bar", "line", "percentage", "pie", "donut"))
        cdata = chart.get("data")
        self.assertIsInstance(cdata, dict, "Chart must carry a data dict.")
        self.assertIsInstance(cdata.get("labels"), list, "Chart data.labels must be a list.")
        datasets = cdata.get("datasets")
        self.assertIsInstance(datasets, list)
        self.assertGreater(len(datasets), 0, "Chart must declare at least one dataset.")
        for ds in datasets:
            self.assertIn("values", ds, "Each chart dataset must have a values list.")
            self.assertIsInstance(ds["values"], list)
            self.assertEqual(len(ds["values"]), len(cdata["labels"]),
                             "Chart dataset values must align with labels.")

    # ---- shape smoke tests: filter-only / pre-existing reports ----

    def test_accommodation_occupancy_summary(self):
        self._assert_report_shape(execute_occupancy())

    def test_accommodation_cost_distribution(self):
        self._assert_report_shape(execute_cost())

    def test_lease_expiry_watchlist(self):
        self._assert_report_shape(execute_lease())

    def test_custody_damage_register(self):
        self._assert_report_shape(execute_custody())

    def test_scheduled_task_compliance(self):
        self._assert_report_shape(execute_task())

    def test_maintenance_backlog(self):
        self._assert_report_shape(execute_maintenance())

    def test_accommodation_ledger_summary(self):
        self._assert_report_shape(execute_ledger_summary())

    def test_supplier_cost_recovery_shape(self):
        self._assert_report_shape(execute_supplier())

    def test_movement_cost_summary(self):
        self._assert_report_shape(execute_mov_summary())

    def test_movement_cost_recovery_register(self):
        self._assert_report_shape(execute_mov_recovery())

    def test_rental_settlement_register(self):
        self._assert_report_shape(execute_rental_settlement())

    def test_salis_payment_register(self):
        self._assert_report_shape(execute_payment())

    # ---- chart reports: shape + chart-dict validity ----

    def test_utility_variance_report_chart(self):
        self._assert_chart_report(execute_utility())

    def test_maintenance_aging_chart(self):
        self._assert_chart_report(execute_maint_aging())

    def test_occupancy_trend_chart(self):
        self._assert_chart_report(execute_occ_trend())

    def test_rental_variance_report_chart(self):
        self._assert_chart_report(execute_rental_variance())

    def test_fuel_reconciliation_chart(self):
        self._assert_chart_report(execute_fuel_recon())

    def test_cost_recovery_aging_chart(self):
        self._assert_chart_report(execute_cost_aging())

    def test_fuel_spend_by_vehicle_chart(self):
        self._assert_chart_report(execute_fuel_spend())

    def test_transport_fulfilment_sla_chart(self):
        self._assert_chart_report(execute_transport_sla())

    # ---- project filter narrows results (server-side WHERE honoured) ----

    def test_project_filter_narrows_results(self):
        """Seed two Accommodation Ledger memo rows under two different projects and
        confirm the Accommodation Cost Distribution report's project filter narrows
        the result set to a single project server-side."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co " + _h(), "default_currency": "SAR",
            "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        cost_center = (frappe.db.get_value("Cost Center", {"is_group": 0, "company": company})
                       or frappe.db.get_value("Cost Center", {"is_group": 0}))
        site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        building = frappe.get_doc({
            "doctype": "Accommodation Building", "building_name": "B " + _h(), "site": site.name,
            "total_capacity": 10, "default_cost_center": cost_center, "annual_rent_sar": 36500,
        }).insert(ignore_permissions=True).name

        project_a = frappe.get_doc({
            "doctype": "Project", "project_name": "PA " + _h(), "company": company,
        }).insert(ignore_permissions=True).name
        project_b = frappe.get_doc({
            "doctype": "Project", "project_name": "PB " + _h(), "company": company,
        }).insert(ignore_permissions=True).name

        # ledger_type is a constrained Select, so isolate seeded rows by the free
        # Data field source_name instead. Each project gets a distinct,
        # marker-prefixed source_name so disjointness is provable from the output.
        prefix = "FILTER-" + _h(6) + "-"
        src_a, src_b = prefix + "A", prefix + "B"
        for project, src in ((project_a, src_a), (project_b, src_b)):
            frappe.get_doc({
                "doctype": "Accommodation Ledger",
                "company": company,
                "posting_date": getdate(),
                "building": building,
                "project": project,
                "ledger_type": "Other",
                "posting_mode": "Operational Memo",
                "employee_daily_share": 100.0,
                "total_site_cost": 100.0,
                "source_name": src,
            }).insert(ignore_permissions=True)

        def _mine(rows):
            return [r for r in rows if (r.get("source_name") or "").startswith(prefix)]

        # Unfiltered (by building only) both rows are visible; adding the project
        # filter must narrow to exactly the one row under project_a. (The report's
        # output rows do not echo `project`, so narrowing is asserted by count of
        # the marker-tagged rows, which is what the server-side WHERE controls.)
        _, all_rows = execute_cost({"building": building})[:2]
        _, a_rows = execute_cost({"building": building, "project": project_a})[:2]
        _, b_rows = execute_cost({"building": building, "project": project_b})[:2]

        self.assertEqual(len(_mine(all_rows)), 2, "Both seeded ledger rows should be visible unfiltered.")
        self.assertEqual(len(_mine(a_rows)), 1, "Project filter must narrow to project_a's single row.")
        self.assertEqual(len(_mine(b_rows)), 1, "Project filter must narrow to project_b's single row.")
        # The two single-project result sets must be disjoint (different rows).
        self.assertEqual(_mine(a_rows)[0]["source_name"], src_a,
                         "project_a filter must return only project_a's row.")
        self.assertEqual(_mine(b_rows)[0]["source_name"], src_b,
                         "project_b filter must return only project_b's row.")
