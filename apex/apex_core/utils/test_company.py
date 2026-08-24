# Copyright (c) 2026, afmcoltd

"""The company defaulting chain the demo seeder and the setup wizard both enter.

``resolve_company_or_any`` is the demo/seed last resort: the configured chain first,
then ANY existing Company so a fresh bench has something to attach. A copy of this in
either caller would let one of them attach a different company than the other on the
same bench, and the mismatch surfaces only once a ledger row carries it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.setup import demo, setup_wizard
from apex.apex_core.utils import company as company_module
from apex.apex_core.utils.company import resolve_company_or_any


class TestResolveCompanyOrAny(FrappeTestCase):
    """The chain's branch, with the configured step stood in for.

    ``resolve_company`` has its own settings-driven behaviour; what is proved here is
    what happens AFTER it answers, which is the step this module adds.
    """

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
        """The tail must return a Company that EXISTS, never a placeholder."""
        company_module.resolve_company = lambda module=None: None
        resolved = resolve_company_or_any()
        existing = frappe.get_all("Company", pluck="name")
        if existing:
            self.assertIn(resolved, existing)
        else:
            self.assertIsNone(resolved)

    def test_a_blank_configured_value_is_not_treated_as_an_answer(self):
        """``resolve_company`` returning "" must fall through, not resolve to blank."""
        company_module.resolve_company = lambda module=None: ""
        resolved = resolve_company_or_any()
        self.assertNotEqual(resolved, "")
        existing = frappe.get_all("Company", pluck="name")
        if existing:
            self.assertIn(resolved, existing)
        else:
            self.assertIsNone(resolved)

    def test_both_seed_callers_enter_through_this_one_resolver(self):
        """A second copy in either caller is the defect this guards."""
        self.assertIs(demo.resolve_company_or_any, resolve_company_or_any)
        self.assertIs(setup_wizard.resolve_company_or_any, resolve_company_or_any)
