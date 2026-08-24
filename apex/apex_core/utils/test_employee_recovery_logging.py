# Copyright (c) 2026, afmcoltd


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
