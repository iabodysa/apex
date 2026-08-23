# Copyright (c) 2026, afmcoltd

"""A misconfigured Recovery Salary Component silently no-ops every scheduled
recovery run. Neither is a Python ``logger`` call — floored at ERROR in
production (frappe/utils/logger.py:12) — nor a document of its own to carry
the outcome, so the refusal is reported through ``frappe.log_error``, a
persisted Error Log entry any System Manager can read in Desk regardless of
the site's logger floor.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.employee_recovery import _recovery_component


class TestRecoveryComponentSurfacesMisconfigurationVisibly(FrappeTestCase):
    def setUp(self):
        self._enabled = frappe.db.get_single_value(
            "Salis Settings", "enable_employee_advance_recovery"
        )
        self._component = frappe.db.get_single_value(
            "Salis Settings", "employee_advance_recovery_component"
        )

    def tearDown(self):
        frappe.db.set_single_value(
            "Salis Settings", "enable_employee_advance_recovery", self._enabled
        )
        frappe.db.set_single_value(
            "Salis Settings", "employee_advance_recovery_component", self._component
        )

    def test_a_missing_component_writes_a_visible_error_log(self):
        frappe.db.set_single_value(
            "Salis Settings", "enable_employee_advance_recovery", 1
        )
        frappe.db.set_single_value(
            "Salis Settings", "employee_advance_recovery_component", None
        )
        before = frappe.db.count("Error Log")

        result = _recovery_component()

        self.assertIsNone(result)
        self.assertGreater(frappe.db.count("Error Log"), before)
