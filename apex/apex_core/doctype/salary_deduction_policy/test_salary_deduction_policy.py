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

# [#p0xvzg]
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
        # [#8ph755]
        doc = _policy(0, {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 5})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_zero_global_cap_allows_zero_rule(self):
        # [#fv28op]
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
        doc.validate()  # [#3vfaf1]

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
        doc.validate()  # [#3vfaf1]

    def test_rule_exceeding_positive_cap_rejected(self):
        doc = _policy(20, {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 30})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_disabled_rule_ignores_cap(self):
        # [#hadxfr]
        doc = _policy(0, {"deduction_type": "Damage", "enabled": 0, "max_percent_of_salary": 40})
        doc.validate()  # [#3vfaf1]

    def test_get_type_rule_gates_on_master_switch_and_enabled(self):
        # [#7smg22]
        component = _deduction_component()
        rule = {"deduction_type": "Damage", "enabled": 1, "max_percent_of_salary": 5,
                "salary_component": component}
        on = _policy(50, rule)
        on.enable_salary_deductions = 1
        self.assertIsNotNone(on.get_type_rule("Damage"), "enabled rule under an on master must return")
        self.assertIsNone(on.get_type_rule("Rent"), "absent type returns None")

        off = _policy(50, dict(rule))
        off.enable_salary_deductions = 0
        self.assertIsNone(off.get_type_rule("Damage"), "master switch off gates every type")


class TestMoveDeductionPatch(FrappeTestCase):
    """The patch must carry an existing Habitat Settings damage value onto the Policy
    Damage rule and turn the global master switch ON (financial safety: an enabled
    deduction must not silently turn off)."""

    def test_patch_moves_damage_value_and_keeps_it_on(self):
        from apex.patches.v1_x import move_deduction_to_salary_policy as patch

        component = _deduction_component()
        # [#75h98h]
        policy = frappe.get_single("Salary Deduction Policy")
        policy.enable_salary_deductions = 0
        policy.type_rules = []
        policy.flags.ignore_validate = True
        policy.save(ignore_permissions=True)

        # [#n4lvp8]
        for field, value in (
            ("enable_damage_deduction", "1"),
            ("damage_salary_component", component),
            ("max_damage_deduction_per_checkout_sar", "350"),
        ):
            frappe.db.sql(
                "DELETE FROM `tabSingles` WHERE doctype=%s AND field=%s",
                ("Habitat Settings", field),
            )
            frappe.db.sql(
                "INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)",
                ("Habitat Settings", field, value),
            )

        patch.execute()

        policy = frappe.get_single("Salary Deduction Policy")
        self.assertEqual(policy.enable_salary_deductions, 1, "an enabled deduction must stay on")
        damage = next((r for r in policy.type_rules if r.deduction_type == "Damage"), None)
        self.assertIsNotNone(damage, "the Damage rule must be created")
        self.assertEqual(damage.enabled, 1)
        self.assertEqual(damage.salary_component, component)
        self.assertEqual(float(damage.cap_amount_per_event), 350.0)

        # [#2l1zdr]
        remaining = frappe.db.sql(
            "SELECT field FROM `tabSingles` WHERE doctype=%s AND field IN %s",
            ("Habitat Settings", tuple(patch.ALL_FIELDS)),
        )
        self.assertEqual(remaining, (), "orphan rows must be deleted after the move")
        patch.execute()  # [#d38q25]


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
