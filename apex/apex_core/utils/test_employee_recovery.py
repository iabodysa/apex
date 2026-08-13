from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from hrms.hr.doctype.employee_advance import employee_advance as native_advance
from hrms.payroll.doctype.additional_salary import additional_salary as native_additional_salary

from apex.apex_core.utils import employee_recovery


class TestEmployeeRecovery(unittest.TestCase):
    def setUp(self):
        frappe.local.flags = frappe._dict(in_test=False)
        frappe.local.request = None

    @patch.object(employee_recovery, "_scheduled_deductions", return_value=0)
    @patch.object(employee_recovery, "_monthly_wage", return_value=1000)
    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_agreed_installment", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_configured_recovery_cap_never_exceeds_fifty_percent(
        self, frappe_mock, _links, _agreed, _pending, _wage, _scheduled
    ):
        frappe_mock.db.get_value.return_value = frappe._dict(
            employee="EMP-1",
            paid_amount=1000,
            return_amount=0,
            docstatus=1,
            custom_source_doctype="Vehicle Incident",
            custom_source_document="VI-1",
        )
        frappe_mock.db.get_single_value.side_effect = [1, 80]

        amount = employee_recovery.compute_recovery_installment(
            "ADV-1", "2026-08-31"
        )

        self.assertEqual(amount, 500)

    @patch.object(employee_recovery, "_pending_installments", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_unpaid_advance_defers_recovery(
        self, frappe_mock, _links, _pending
    ):
        frappe_mock.db.get_value.return_value = frappe._dict(
            employee="EMP-1",
            paid_amount=0,
            return_amount=0,
            docstatus=1,
            custom_source_doctype="Vehicle Incident",
            custom_source_document="VI-1",
        )

        self.assertEqual(
            employee_recovery.compute_recovery_installment(
                "ADV-1", "2026-08-31"
            ),
            0,
        )

    @patch.object(employee_recovery, "_scheduled_deductions", return_value=0)
    @patch.object(employee_recovery, "_monthly_wage", return_value=1000)
    @patch.object(employee_recovery, "_pending_installments", return_value=200)
    @patch.object(employee_recovery, "_agreed_installment", return_value=0)
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_existing_draft_installment_defers_cleared_balance(
        self, frappe_mock, _links, _agreed, _pending, _wage, _scheduled
    ):
        frappe_mock.db.get_value.return_value = frappe._dict(
            employee="EMP-1",
            paid_amount=200,
            return_amount=0,
            docstatus=1,
            custom_source_doctype="Vehicle Incident",
            custom_source_document="VI-1",
        )

        self.assertEqual(
            employee_recovery.compute_recovery_installment(
                "ADV-1", "2026-08-31"
            ),
            0,
        )

    @patch.object(employee_recovery, "find_recovery_advance", return_value="ADV-1")
    @patch.object(employee_recovery, "_source_link_available", return_value=True)
    @patch.object(employee_recovery, "frappe")
    def test_source_is_locked_before_duplicate_advance_check(
        self, frappe_mock, _links, find_advance
    ):
        sequence = []
        frappe_mock.logger.return_value = MagicMock()
        frappe_mock.db.get_value.side_effect = lambda *args, **kwargs: sequence.append(
            (args, kwargs)
        ) or "VI-1"
        find_advance.side_effect = lambda *args: sequence.append("find") or "ADV-1"

        result = employee_recovery.raise_recovery_advance(
            "Vehicle Incident", "VI-1", "EMP-1", 100, "Damage recovery"
        )

        self.assertEqual(result, "ADV-1")
        self.assertEqual(sequence[0][0][:3], ("Vehicle Incident", "VI-1", "name"))
        self.assertTrue(sequence[0][1]["for_update"])
        self.assertEqual(sequence[1], "find")

    @patch.object(employee_recovery, "compute_recovery_installment", return_value=100)
    @patch.object(employee_recovery, "_recovery_component", return_value="Recovery")
    @patch.object(native_advance, "create_return_through_additional_salary")
    @patch.object(employee_recovery, "frappe")
    def test_scheduler_locks_advance_and_uses_native_draft_factory(
        self, frappe_mock, native_factory, _component, _amount
    ):
        advance = SimpleNamespace(name="ADV-1")
        installment = MagicMock(name="installment")
        installment.name = "AS-1"
        native_factory.return_value = installment
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.exists.return_value = False
        frappe_mock.logger.return_value = MagicMock()

        result = employee_recovery.schedule_recovery_deduction(
            "ADV-1", "2026-08-31"
        )

        frappe_mock.get_doc.assert_called_once_with(
            "Employee Advance", "ADV-1", for_update=True
        )
        native_factory.assert_called_once_with(advance)
        self.assertEqual(installment.salary_component, "Recovery")
        self.assertEqual(installment.amount, 100)
        self.assertEqual(installment.payroll_date, "2026-08-31")
        installment.insert.assert_called_once_with(ignore_permissions=True)
        frappe_mock.db.set_value.assert_not_called()
        self.assertEqual(result, "AS-1")

    @patch.object(employee_recovery, "frappe")
    def test_existing_draft_or_submitted_installment_is_not_duplicated(
        self, frappe_mock
    ):
        advance = SimpleNamespace(name="ADV-1")
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.exists.return_value = "AS-1"

        result = employee_recovery.schedule_recovery_deduction(
            "ADV-1", "2026-08-31"
        )

        self.assertIsNone(result)
        duplicate_filters = frappe_mock.db.exists.call_args.args[1]
        self.assertEqual(duplicate_filters["docstatus"], ["<", 2])
        frappe_mock.get_doc.assert_called_once_with(
            "Employee Advance", "ADV-1", for_update=True
        )

    @patch.object(native_additional_salary, "frappe")
    def test_native_additional_salary_submit_and_cancel_reverse_advance(
        self, frappe_mock
    ):
        advance = MagicMock(name="advance")
        frappe_mock.get_doc.return_value = advance
        frappe_mock.db.get_value.side_effect = [200, 300]
        installment = SimpleNamespace(
            ref_doctype="Employee Advance",
            ref_docname="ADV-1",
            amount=100,
            docstatus=1,
        )

        native_additional_salary.AdditionalSalary.update_return_amount_in_employee_advance(
            installment
        )
        installment.docstatus = 2
        native_additional_salary.AdditionalSalary.update_return_amount_in_employee_advance(
            installment
        )

        self.assertEqual(
            frappe_mock.db.set_value.call_args_list[0].args,
            ("Employee Advance", "ADV-1", "return_amount", 300),
        )
        self.assertEqual(
            frappe_mock.db.set_value.call_args_list[1].args,
            ("Employee Advance", "ADV-1", "return_amount", 200),
        )
        self.assertEqual(advance.set_status.call_count, 2)


if __name__ == "__main__":
    unittest.main()
