# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for logistay.utils.cost_center resolution precedence.

The per-field master reads are mocked at the module's ``_field`` seam, so the
Employee -> Department -> Company (and Project) precedence is exercised without
a live site.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.logistay.utils import cost_center


def _field_map(values):
    """Fake ``_field(doctype, name, fieldname)`` keyed on (doctype, fieldname)."""

    def _fake(doctype, name, fieldname):
        if not name:
            return None
        return values.get((doctype, fieldname))

    return _fake


class TestResolveEmployeeCostCenter(unittest.TestCase):
    def test_employee_own_cost_center_wins(self):
        values = {("Employee", "payroll_cost_center"): "CC-EMP"}
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(
                cost_center.resolve_employee_cost_center("E-1", "Acme"), "CC-EMP"
            )

    def test_employee_own_cost_center_wins_over_department_and_company(self):
        """All three candidates present at once: only the precedence order, not a
        single-candidate short circuit, can be what selects the Employee's own value."""
        values = {
            ("Employee", "payroll_cost_center"): "CC-EMP",
            ("Employee", "department"): "D-1",
            ("Department", "payroll_cost_center"): "CC-DEPT",
            ("Company", "cost_center"): "CC-CO",
        }
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(
                cost_center.resolve_employee_cost_center("E-1", "Acme"), "CC-EMP"
            )

    def test_department_cost_center_wins_over_company_when_employee_absent(self):
        """Employee's own value absent, Department and Company both present: only
        the precedence order can be what selects Department over Company."""
        values = {
            ("Employee", "payroll_cost_center"): None,
            ("Employee", "department"): "D-1",
            ("Department", "payroll_cost_center"): "CC-DEPT",
            ("Company", "cost_center"): "CC-CO",
        }
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(
                cost_center.resolve_employee_cost_center("E-1", "Acme"), "CC-DEPT"
            )

    def test_falls_back_to_department_cost_center(self):
        values = {
            ("Employee", "payroll_cost_center"): None,
            ("Employee", "department"): "D-1",
            ("Department", "payroll_cost_center"): "CC-DEPT",
        }
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(
                cost_center.resolve_employee_cost_center("E-1", "Acme"), "CC-DEPT"
            )

    def test_falls_back_to_company_default(self):
        values = {("Company", "cost_center"): "CC-CO"}
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(
                cost_center.resolve_employee_cost_center("E-1", "Acme"), "CC-CO"
            )

    def test_unresolved_returns_none(self):
        with mock.patch.object(cost_center, "_field", _field_map({})):
            self.assertIsNone(cost_center.resolve_employee_cost_center("E-1", "Acme"))
            self.assertIsNone(cost_center.resolve_employee_cost_center("E-1", None))

    def test_no_employee_short_circuits(self):
        with mock.patch.object(cost_center, "_field") as field:
            self.assertIsNone(cost_center.resolve_employee_cost_center(None))
            field.assert_not_called()


class TestResolveProjectCostCenter(unittest.TestCase):
    def test_reads_project_cost_center(self):
        values = {("Project", "cost_center"): "CC-PRJ"}
        with mock.patch.object(cost_center, "_field", _field_map(values)):
            self.assertEqual(cost_center.resolve_project_cost_center("P-1"), "CC-PRJ")

    def test_no_project_short_circuits(self):
        with mock.patch.object(cost_center, "_field") as field:
            self.assertIsNone(cost_center.resolve_project_cost_center(None))
            field.assert_not_called()


if __name__ == "__main__":
    unittest.main()
