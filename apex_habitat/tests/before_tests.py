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
	# The full suite creates far more than Frappe's default cap of 60 new Users
	# per 60 seconds, which raises "Throttled" in many setUpClass blocks. Raise
	# the cap for the whole test run. It MUST be an int: a string (e.g. from
	# `bench set-config`) breaks the `int > limit` comparison in Frappe's
	# throttle_user_creation. before_tests runs before any user is created.
	frappe.local.conf["throttle_user_limit"] = 100000

	from erpnext.setup.utils import before_tests as erpnext_before_tests

	erpnext_before_tests()
	frappe.db.commit()
