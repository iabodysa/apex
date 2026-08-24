# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup import demo, setup_wizard
from apex.apex_core.utils import company as company_module
from apex.apex_core.utils.company import resolve_company_or_any


class TestResolveCompanyOrAny(FrappeTestCase):

    def setUp(self):
        self._real = company_module.resolve_company

    def tearDown(self):
        company_module.resolve_company = self._real

    def test_the_configured_company_wins_and_the_tail_is_not_reached(self):
        company_module.resolve_company = lambda module=None: "Configured Co"
        self.assertEqual(resolve_company_or_any(), "Configured Co")
        self.assertEqual(resolve_company_or_any("Habitat"), "Configured Co")

    def test_the_module_argument_reaches_the_configured_step(self):
        seen = []
        company_module.resolve_company = lambda module=None: seen.append(module) or "Co"
        resolve_company_or_any("Salis")
        self.assertEqual(seen, ["Salis"])

    def test_an_unconfigured_chain_falls_back_to_a_real_company(self):
        company_module.resolve_company = lambda module=None: None
        resolved = resolve_company_or_any()
        existing = frappe.get_all("Company", pluck="name")
        if existing:
            self.assertIn(resolved, existing)
        else:
            self.assertIsNone(resolved)

    def test_a_blank_configured_value_is_not_treated_as_an_answer(self):
        company_module.resolve_company = lambda module=None: ""
        resolved = resolve_company_or_any()
        self.assertNotEqual(resolved, "")
        existing = frappe.get_all("Company", pluck="name")
        if existing:
            self.assertIn(resolved, existing)
        else:
            self.assertIsNone(resolved)

    def test_both_seed_callers_enter_through_this_one_resolver(self):
        self.assertIs(demo.resolve_company_or_any, resolve_company_or_any)
        self.assertIs(setup_wizard.resolve_company_or_any, resolve_company_or_any)
