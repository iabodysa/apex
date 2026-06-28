# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Salary Deduction Policy global-cap gate.

The load-bearing case is the 0-vs-unset distinction: a deliberate 0% global cap
(deductions disabled by ceiling) must be HONOURED, not silently treated as unset
and replaced by the 50% legal ceiling. These build the Single in memory and run
the controller's own ``validate`` -- no persistence is needed to exercise the gate,
and the cap check fires before the Salary Component check, so a violating row needs
no component.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

# Payment Gateway lives in the (uninstalled) payments app; skip it in the dependency closure.
test_ignore = ["Payment Gateway"]


def _policy(global_cap, rule):
    """An in-memory (unsaved) Salary Deduction Policy Single carrying one type rule."""
    doc = frappe.get_doc(
        {
            "doctype": "Salary Deduction Policy",
            "global_max_percent_of_salary": global_cap,
            "type_rules": [rule],
        }
    )
    return doc


class TestSalaryDeductionPolicy(FrappeTestCase):

    def test_zero_global_cap_is_honoured_not_treated_as_unset(self):
        # A deliberate 0% ceiling must reject an enabled rule that wants 5% -- the gate
        # must fire (5 > 0), not fall back to the 50% default and let it through.
        doc = _policy(0, {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 5})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_zero_global_cap_allows_zero_rule(self):
        # 0% rule under a 0% cap is not a violation (0 > 0 is False) -- no false positive.
        # The rule names a component so it passes the downstream component check too.
        component = _deduction_component()
        doc = _policy(
            0,
            {
                "deduction_type": "Damage",
                "enabled": 1,
                "max_percent_of_salary": 0,
                "salary_component": component,
            },
        )
        doc.validate()  # must not raise

    def test_positive_cap_allows_within_cap_rule(self):
        component = _deduction_component()
        doc = _policy(
            50,
            {
                "deduction_type": "Damage",
                "enabled": 1,
                "max_percent_of_salary": 10,
                "salary_component": component,
            },
        )
        doc.validate()  # must not raise

    def test_rule_exceeding_positive_cap_rejected(self):
        doc = _policy(20, {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 30})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_disabled_rule_ignores_cap(self):
        # A disabled row may hold any draft value; it never fires while disabled.
        doc = _policy(0, {"deduction_type": "Damage", "enabled": 0, "max_percent_of_salary": 40})
        doc.validate()  # must not raise


def _deduction_component():
    """Return a Salary Component of type Deduction, creating it if needed."""
    name = "QA Operational Deduction"
    if not frappe.db.exists("Salary Component", name):
        frappe.get_doc(
            {
                "doctype": "Salary Component",
                "salary_component": name,
                "type": "Deduction",
            }
        ).insert(ignore_permissions=True)
    return name
