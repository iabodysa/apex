# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.report.accommodation_occupancy_summary.accommodation_occupancy_summary import execute as execute_occupancy
from apex_habitat.habitat.report.accommodation_cost_distribution.accommodation_cost_distribution import execute as execute_cost
from apex_habitat.habitat.report.lease_expiry_watchlist.lease_expiry_watchlist import execute as execute_lease
from apex_habitat.habitat.report.utility_variance_report.utility_variance_report import execute as execute_utility
from apex_habitat.habitat.report.custody_damage_register.custody_damage_register import execute as execute_custody
from apex_habitat.habitat.report.scheduled_task_compliance.scheduled_task_compliance import execute as execute_task
from apex_habitat.habitat.report.maintenance_backlog.maintenance_backlog import execute as execute_maintenance


class TestReports(ApexHabitatTestCase):
    """Smoke-test the report execute() entrypoints.

    These tests only verify that each report's `execute()` returns a valid
    (columns, data) shape without raising. They intentionally do not assert
    that data is non-empty, because in a fresh CI database there are no
    seeded transactional records. Data-content correctness is covered by
    the dedicated lifecycle / scheduler tests that create their own records.
    """

    def _assert_report_shape(self, result):
        self.assertIsInstance(result, tuple, "Report execute() must return a tuple.")
        self.assertGreaterEqual(len(result), 2, "Report execute() must return at least (columns, data).")
        columns, data = result[0], result[1]
        self.assertIsNotNone(columns, "Report columns must not be None.")
        self.assertIsInstance(columns, list)
        self.assertGreater(len(columns), 0, "Report must declare at least one column.")
        self.assertIsInstance(data, list, "Report data must be a list.")

    def test_accommodation_occupancy_summary(self):
        self._assert_report_shape(execute_occupancy())

    def test_accommodation_cost_distribution(self):
        self._assert_report_shape(execute_cost())

    def test_lease_expiry_watchlist(self):
        self._assert_report_shape(execute_lease())

    def test_utility_variance_report(self):
        self._assert_report_shape(execute_utility())

    def test_custody_damage_register(self):
        self._assert_report_shape(execute_custody())

    def test_scheduled_task_compliance(self):
        self._assert_report_shape(execute_task())

    def test_maintenance_backlog(self):
        self._assert_report_shape(execute_maintenance())
