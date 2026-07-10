# Copyright (c) 2026, AFMCO and contributors
"""Test-site bootstrap for the apex_habitat suite.

apex_habitat builds on ERPNext and HRMS. The framework auto-creates master data
(Warehouse Types, fiscal year, UOMs) the first time a Company is inserted, but a
fresh CI site has none of it until the setup wizard runs. Any test that inserts a
Company would otherwise fail with:

    LinkValidationError: Could not find Warehouse Type: Transit

Frappe invokes this ``before_tests`` hook once, before the suite runs. We reuse
ERPNext's own setup-wizard bootstrap (idempotent — it no-ops when a Company
already exists) so every test inherits a fully provisioned site.
"""

import frappe


def before_tests():
	from erpnext.setup.utils import before_tests as erpnext_before_tests

	erpnext_before_tests()
	frappe.db.commit()

	# P-148: record the pre-suite Accommodation Building set so purge_test_buildings()
	# (invoked from building-creating modules' tearDownModule) restores the post-suite
	# building count to this baseline.
	from apex_habitat.tests import factories

	factories.snapshot_building_baseline()

