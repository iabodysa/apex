# Copyright (c) 2026, AFMCO and contributors
"""Test-site bootstrap for the apex suite.

apex builds on ERPNext and HRMS. The framework auto-creates master data
(Warehouse Types, fiscal year, UOMs) the first time a Company is inserted, but a
fresh CI site has none of it until the setup wizard runs. Any test that inserts a
Company would otherwise fail with:

    LinkValidationError: Could not find Warehouse Type: Transit

It reuses ERPNext's own setup-wizard bootstrap (idempotent — it no-ops when a
Company already exists) so every test inherits a fully provisioned site.

NOT WIRED, and measured rather than assumed: ``apex/hooks.py`` declares no
``before_tests`` key, so ``frappe.get_hooks("before_tests")`` on this bench answers
frappe, erpnext and hrms and never apex — this function has never run. The site is
provisioned anyway, because ``erpnext.setup.utils.before_tests`` is in that answer
already and does the same work. Registering apex's key would make it the third
caller of an idempotent bootstrap; leaving it unregistered leaves this module dead.
Either is defensible, and the choice belongs with whoever owns hooks.py — what is
not defensible is a docstring claiming a hook runs when nothing calls it.
"""

import frappe


def before_tests():
    from erpnext.setup.utils import before_tests as erpnext_before_tests

    erpnext_before_tests()
    frappe.db.commit()

