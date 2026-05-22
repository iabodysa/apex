# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.habitat.report.accommodation_occupancy_summary.accommodation_occupancy_summary import execute as execute_occupancy
from apex_habitat.habitat.report.accommodation_cost_distribution.accommodation_cost_distribution import execute as execute_cost
from apex_habitat.habitat.report.lease_expiry_watchlist.lease_expiry_watchlist import execute as execute_lease
from apex_habitat.habitat.report.utility_variance_report.utility_variance_report import execute as execute_utility
from apex_habitat.habitat.report.custody_damage_register.custody_damage_register import execute as execute_custody
from apex_habitat.habitat.report.scheduled_task_compliance.scheduled_task_compliance import execute as execute_task
from apex_habitat.habitat.report.maintenance_backlog.maintenance_backlog import execute as execute_maintenance


class TestReports(ApexHabitatTestCase):
    def test_accommodation_occupancy_summary(self):
        # Current implementation returns hardcoded empty data list.
        # This test checks that when records exist, the report returns data.
        columns, data = execute_occupancy()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Accommodation Occupancy Summary should return data when assignments exist.")

    def test_accommodation_cost_distribution(self):
        columns, data = execute_cost()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Accommodation Cost Distribution should return data when cost records exist.")

    def test_lease_expiry_watchlist(self):
        columns, data = execute_lease()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Lease Expiry Watchlist should return data when leases exist.")

    def test_utility_variance_report(self):
        columns, data = execute_utility()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Utility Variance Report should return data when utility bills exist.")

    def test_custody_damage_register(self):
        columns, data = execute_custody()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Custody Damage Register should return data when custody damage assessments exist.")

    def test_scheduled_task_compliance(self):
        columns, data = execute_task()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Scheduled Task Compliance should return data when scheduled tasks exist.")

    def test_maintenance_backlog(self):
        columns, data = execute_maintenance()
        self.assertIsNotNone(columns)
        self.assertTrue(len(data) > 0, "Maintenance Backlog should return data when maintenance requests exist.")
